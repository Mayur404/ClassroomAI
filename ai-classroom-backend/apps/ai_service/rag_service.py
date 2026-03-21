"""
Local RAG Service — Chunking, Embedding, Vector Search using ChromaDB.
All processing happens locally. Only final Q&A uses Gemini.
"""
import logging
import os
import re

import chromadb
from chromadb.utils import embedding_functions
from django.conf import settings

logger = logging.getLogger(__name__)

# Persistent ChromaDB storage
CHROMA_DIR = os.path.join(settings.MEDIA_ROOT, "chromadb")
os.makedirs(CHROMA_DIR, exist_ok=True)

_client = chromadb.PersistentClient(path=CHROMA_DIR)

# Use the default sentence-transformers model for embeddings (all-MiniLM-L6-v2)
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def _get_collection(course_id: int):
    """Get or create a ChromaDB collection for a specific course."""
    return _client.get_or_create_collection(
        name=f"course_{course_id}",
        embedding_function=_embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    # Clean up the text
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    words = text.split()
    chunks = []

    if len(words) <= chunk_size:
        return [text.strip()] if text.strip() else []

    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap

    return chunks


def extract_topics_from_chunks(chunks: list[str]) -> list[str]:
    """Extract topic summaries from chunks (first meaningful line of each chunk)."""
    topics = []
    seen = set()
    for chunk in chunks[:15]:  # Look at first 15 chunks
        # Take the first sentence or line as a topic hint
        lines = chunk.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 10 and line.lower() not in seen:
                seen.add(line.lower())
                topics.append(line[:80])  # Cap at 80 chars
                break
    return topics[:10]  # Return max 10 topics


def index_course_materials(course_id: int, text: str) -> dict:
    """Chunk text, embed it, and store in ChromaDB. Returns indexing stats."""
    collection = _get_collection(course_id)

    # Clear old data for this course
    try:
        existing = collection.count()
        if existing > 0:
            all_ids = collection.get()["ids"]
            if all_ids:
                collection.delete(ids=all_ids)
    except Exception:
        pass

    # Chunk the document
    chunks = chunk_text(text)
    if not chunks:
        return {"status": "FAILED", "error": "No content to index."}

    # Store chunks with IDs
    ids = [f"chunk_{course_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"course_id": course_id, "chunk_index": i} for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        ids=ids,
        metadatas=metadatas,
    )

    topics = extract_topics_from_chunks(chunks)

    logger.info(f"Indexed {len(chunks)} chunks for course {course_id}")

    return {
        "status": "SUCCESS",
        "num_chunks": len(chunks),
        "topics": topics,
    }


def search_course(course_id: int, query: str, top_k: int = 5) -> list[str]:
    """Search for the most relevant chunks given a query."""
    collection = _get_collection(course_id)

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
    )

    return results["documents"][0] if results["documents"] else []
