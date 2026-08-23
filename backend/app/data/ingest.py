from app.core.llm import embed_text, generate_for_tier
from app.data.database import document_exists, insert_document



def classify_chunk(chunk_text: str) -> str:
    prompt = f"""Classify this text into exactly one category: 'guidelines', 'past_films', or 'scripts'.
Respond with ONLY the category word, nothing else.

Text: {chunk_text}"""

    # No override support here: /ingest doesn't take one (see main.py — only
    # /run-agent does). A GeminiQuotaExhausted here isn't caught locally, so
    # it propagates through ingest_document's per-chunk loop up to the
    # /ingest endpoint, which is what actually reports it.
    result = generate_for_tier("FAST", "You are a document classifier.", prompt)
    result = result.strip().lower()

    if result in ["guidelines", "past_films", "scripts"]:
        return result
    return "scripts"

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

    for chunk in chunks:
        collection = classify_chunk(chunk)
        if document_exists(collection, chunk):
            continue
        embedding = embed_text(chunk)
        doc_id = insert_document(collection, chunk, metadata, embedding)
        inserted_ids.append(doc_id)

    return inserted_ids