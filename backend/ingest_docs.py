import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
load_dotenv()

from app.core.llm import embed_batch
from app.data.database import _execute, insert_document

def chunk_markdown(text: str, words_per_chunk: int = 300, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    step = words_per_chunk - overlap
    if step <= 0:
        step = words_per_chunk
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + words_per_chunk])
        chunks.append(chunk)
    return chunks

def chunk_code(text: str, lines_per_chunk: int = 50, overlap: int = 15) -> list[tuple[int, str]]:
    lines = text.split('\n')
    chunks = []
    step = lines_per_chunk - overlap
    if step <= 0:
        step = lines_per_chunk
    
    for i in range(0, len(lines), step):
        chunk_lines = lines[i:i + lines_per_chunk]
        chunks.append((i + 1, "\n".join(chunk_lines)))
    return chunks

def process_and_insert(collection: str, chunks_data: list[tuple[str, dict]]):
    """chunks_data is a list of (text, metadata)"""
    if not chunks_data:
        return
        
    texts = [item[0] for item in chunks_data]
    print(f"Embedding {len(texts)} chunks for {collection}...")
    
    # Batch embeddings to save time
    batch_size = 20
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        try:
            embeddings = embed_batch(batch)
            all_embeddings.extend(embeddings)
            print(f"  Embedded {len(all_embeddings)}/{len(texts)}")
        except Exception as e:
            print(f"Error embedding batch: {e}")
            raise

    for i, (text, metadata) in enumerate(chunks_data):
        insert_document(collection, text, metadata, all_embeddings[i])

def ingest_all():
    print("Clearing old help documentation...")
    _execute("DELETE FROM documents WHERE collection IN ('client_help', 'admin_help')")

    root_dir = Path(__file__).parent.parent
    
    collections = {
        'client_help': [],
        'admin_help': []
    }

    print("Reading docs/client...")
    for path in (root_dir / 'docs' / 'client').rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        for chunk in chunk_markdown(text):
            collections['client_help'].append((chunk, {"source_path": str(path.relative_to(root_dir))}))

    print("Reading docs/admin...")
    admin_dir = root_dir / 'docs' / 'admin'
    if admin_dir.exists():
        for path in admin_dir.rglob('*.md'):
            text = path.read_text(encoding='utf-8')
            for chunk in chunk_markdown(text):
                collections['admin_help'].append((chunk, {"source_path": str(path.relative_to(root_dir))}))

    for collection_name, chunks in collections.items():
        print(f"Processing {len(chunks)} chunks for {collection_name}...")
        process_and_insert(collection_name, chunks)

if __name__ == "__main__":
    ingest_all()
    print("Done!")
