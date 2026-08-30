from app.core.llm import embed_text, generate_for_tier
from app.data.database import document_exists, insert_document



def classify_document(text: str, metadata: dict = None) -> str:
    if metadata and metadata.get("collection"):
        return metadata["collection"]

    filename = (metadata or {}).get("filename", "").lower()
    sample = text[:2000].lower()

    # Fast keyword heuristics to save LLM quota
    if any(k in filename or k in sample for k in ["guideline", "act", "rule", "cbfc", "compliance", "policy"]):
        return "guidelines"
    if any(k in filename or k in sample for k in ["past_film", "box_office", "historical_film", "comparable"]):
        return "past_films"

    # LLM classification ran ONCE on the first 1000 chars if heuristics miss
    prompt = f"""Classify this document into exactly one category: 'guidelines', 'past_films', or 'scripts'.
Respond with ONLY the category word, nothing else.

Filename: {filename}
Sample: {text[:1000]}"""

    try:
        result = generate_for_tier("FAST", "You are a document classifier.", prompt)
        result = result.strip().lower()
        if result in ["guidelines", "past_films", "scripts"]:
            return result
    except Exception:
        pass

    return "scripts"


def classify_chunk(chunk_text: str) -> str:
    """Legacy alias for backward compatibility with unit tests."""
    return classify_document(chunk_text)


def chunk_text(text: str, words_per_chunk: int = 300, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    step = words_per_chunk - overlap

    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + words_per_chunk])
        chunks.append(chunk)
        if i + words_per_chunk >= len(words):
            break

    return chunks


def ingest_document(text: str, metadata: dict) -> list[int]:
    if not text or not text.strip():
        raise ValueError("Cannot ingest empty text")

    chunks = chunk_text(text)
    inserted_ids = []

    # Classify the document ONCE for the entire PDF/document
    collection = classify_document(text, metadata)

    for chunk in chunks:
        if document_exists(collection, chunk):
            continue
        embedding = embed_text(chunk)
        doc_id = insert_document(collection, chunk, metadata, embedding)
        inserted_ids.append(doc_id)

    return inserted_ids