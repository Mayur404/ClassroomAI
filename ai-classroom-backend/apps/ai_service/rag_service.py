"""
Local RAG service with offline-safe fallbacks.
"""
from collections import OrderedDict
import hashlib
import logging
import math
import os
import re

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.utils import embedding_functions
from django.conf import settings
import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

CHROMA_DIR = os.path.join(settings.MEDIA_ROOT, "chromadb")
os.makedirs(CHROMA_DIR, exist_ok=True)

_client = chromadb.PersistentClient(path=CHROMA_DIR)
_embedding_function = None
_embedding_backend = None
_ollama_session = requests.Session()
_ollama_session.mount("http://", HTTPAdapter(pool_connections=12, pool_maxsize=12))
_ollama_session.mount("https://", HTTPAdapter(pool_connections=12, pool_maxsize=12))
OLLAMA_EMBED_URL = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed"
LEXICAL_CHUNK_CACHE_LIMIT = 96
SEARCH_RESULT_CACHE_LIMIT = 192
_lexical_chunk_cache = OrderedDict()
_search_result_cache = OrderedDict()
TOPIC_NOISE_RE = re.compile(
    r"(attendance|deadline|submission|grading|marks|weightage|office hours|contact|email|quiz|exam|project|policy)",
    re.IGNORECASE,
)
TOPIC_VERB_SPLIT_RE = re.compile(
    r"\s+(?:is|are|covers?|includes?|focuses on|introduces?|explores?|describes?|explains?)\b",
    re.IGNORECASE,
)


class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic fallback embedding function that works fully offline."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Documents):
        embeddings = []
        for document in input:
            tokens = re.findall(r"[a-z0-9]+", (document or "").lower())
            vector = [0.0] * self.dimensions
            if not tokens:
                vector[0] = 1.0
                embeddings.append(vector)
                continue

            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign

            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            embeddings.append([value / norm for value in vector])

        return embeddings

    @staticmethod
    def name() -> str:
        return "hash-fallback"

    @staticmethod
    def build_from_config(config):
        return HashEmbeddingFunction(dimensions=config.get("dimensions", 384))

    def get_config(self):
        return {"dimensions": self.dimensions}

    def default_space(self):
        return "cosine"


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """Embedding function backed by Ollama's /api/embed endpoint."""

    def __init__(self, model_name: str, keep_alive: str = "30m") -> None:
        self.model_name = model_name
        self.keep_alive = keep_alive

    def __call__(self, input: Documents):
        documents = list(input)
        if not documents:
            return []

        response = _ollama_session.post(
            OLLAMA_EMBED_URL,
            json={
                "model": self.model_name,
                "input": documents,
                "keep_alive": self.keep_alive,
                "truncate": True,
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings") or []
        if not embeddings:
            raise ValueError(f"Ollama embedding model {self.model_name} returned no embeddings.")
        return embeddings

    def ping(self) -> None:
        _ = self(["embedding health check"])

    @staticmethod
    def name() -> str:
        return "ollama-embed"

    @staticmethod
    def build_from_config(config):
        return OllamaEmbeddingFunction(
            model_name=config["model_name"],
            keep_alive=config.get("keep_alive", "30m"),
        )

    def get_config(self):
        return {
            "model_name": self.model_name,
            "keep_alive": self.keep_alive,
        }

    def default_space(self):
        return "cosine"


def get_embedding_function():
    global _embedding_function, _embedding_backend

    if _embedding_function is not None:
        return _embedding_function

    ollama_embed_model = getattr(settings, "OLLAMA_EMBED_MODEL", "").strip()
    ollama_embed_keep_alive = getattr(settings, "OLLAMA_EMBED_KEEP_ALIVE", "30m")
    if ollama_embed_model:
        try:
            candidate = OllamaEmbeddingFunction(
                model_name=ollama_embed_model,
                keep_alive=ollama_embed_keep_alive,
            )
            candidate.ping()
            _embedding_function = candidate
            _embedding_backend = f"ollama:{ollama_embed_model}"
            logger.info("Using Ollama embeddings via %s", ollama_embed_model)
            return _embedding_function
        except Exception as exc:
            logger.warning(
                "Falling back from Ollama embeddings model %s because it is unavailable: %s",
                ollama_embed_model,
                exc,
            )

    try:
        _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
            local_files_only=True,
        )
        _embedding_backend = "sentence-transformer"
    except Exception as exc:
        logger.warning(
            "Falling back to hash embeddings because the local sentence-transformer "
            "model is unavailable: %s",
            exc,
        )
        _embedding_function = HashEmbeddingFunction()
        _embedding_backend = "hash-fallback"

    return _embedding_function


def _collection_backend_suffix() -> str:
    backend = _embedding_backend or "default"
    slug = re.sub(r"[^a-z0-9]+", "_", backend.lower()).strip("_")
    return slug[:50] or "default"


def _cache_put(cache: OrderedDict, key, value, limit: int):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


def _invalidate_course_search_cache(course_id: int):
    stale_keys = [key for key in _search_result_cache if key[0] == course_id]
    for key in stale_keys:
        _search_result_cache.pop(key, None)


def _invalidate_material_cache(course_id: int, material_id: int | None = None):
    if material_id is not None:
        stale_keys = [key for key in _lexical_chunk_cache if key[0] == material_id]
        for key in stale_keys:
            _lexical_chunk_cache.pop(key, None)
    _invalidate_course_search_cache(course_id)


def _text_signature(text: str) -> str:
    return hashlib.blake2b((text or "").encode("utf-8"), digest_size=8).hexdigest()


def _normalized_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def _get_collection(course_id: int):
    get_embedding_function()
    return _client.get_or_create_collection(
        name=f"course_{course_id}_{_collection_backend_suffix()}",
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def _get_course_collection_names(course_id: int) -> list[str]:
    prefix = f"course_{course_id}"
    names = []
    try:
        for collection in _client.list_collections():
            name = collection.name if hasattr(collection, "name") else str(collection)
            if name.startswith(prefix):
                names.append(name)
    except Exception:
        current_name = f"{prefix}_{_collection_backend_suffix()}"
        names.append(current_name)

    current_name = f"{prefix}_{_collection_backend_suffix()}"
    if current_name not in names:
        names.append(current_name)
    return names


def _looks_like_outline_line(line: str) -> bool:
    return bool(
        re.match(r"^(week|module|unit|chapter|lesson|topic|lecture|session|class|part|section)\b", line, re.IGNORECASE)
        or re.match(r"^(\(?\d+[a-z]?\)?[\.\):-]|[A-Z][\.\)])\s+", line)
        or line.startswith("- ")
        or line.endswith(":")
    )


def _split_text_blocks(text: str) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text or "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)

    blocks = []
    current = []
    for raw_line in normalized.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if current:
                blocks.append(" ".join(current).strip())
                current = []
            continue

        if _looks_like_outline_line(line):
            if current:
                blocks.append(" ".join(current).strip())
                current = []
            blocks.append(line)
            continue

        current.append(line)

    if current:
        blocks.append(" ".join(current).strip())

    return [block for block in blocks if block]


def _tail_blocks_for_overlap(blocks: list[str], overlap_words: int) -> list[str]:
    tail = []
    words = 0
    for block in reversed(blocks):
        tail.insert(0, block)
        words += len(block.split())
        if words >= overlap_words:
            break
    return tail


def _adaptive_chunk_settings(total_words: int, chunk_size: int, overlap: int) -> tuple[int, int]:
    if chunk_size != 500 or overlap != 100:
        return chunk_size, overlap
    if total_words >= 6000:
        return 900, 120
    if total_words >= 2500:
        return 750, 100
    return 600, 80


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split text into paragraph-aware overlapping chunks for indexing and lexical fallback search."""
    blocks = _split_text_blocks(text)
    if not blocks:
        return []

    total_words = sum(len(block.split()) for block in blocks)
    chunk_size, overlap = _adaptive_chunk_settings(total_words, chunk_size, overlap)

    if total_words <= chunk_size:
        return ["\n".join(blocks).strip()]

    chunks = []
    current_blocks = []
    current_word_count = 0

    for block in blocks:
        block_word_count = len(block.split())
        if current_blocks and current_word_count + block_word_count > chunk_size:
            chunks.append("\n".join(current_blocks).strip())
            current_blocks = _tail_blocks_for_overlap(current_blocks, overlap)
            current_word_count = sum(len(item.split()) for item in current_blocks)

        current_blocks.append(block)
        current_word_count += block_word_count

    if current_blocks:
        chunks.append("\n".join(current_blocks).strip())

    deduped = []
    seen = set()
    for chunk in chunks:
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)

    return deduped


def _cached_material_chunks(material_id: int, text: str) -> tuple[str, ...]:
    key = (material_id, _text_signature(text))
    cached = _lexical_chunk_cache.get(key)
    if cached is not None:
        _lexical_chunk_cache.move_to_end(key)
        return cached

    chunks = tuple(chunk_text(text))
    _cache_put(_lexical_chunk_cache, key, chunks, LEXICAL_CHUNK_CACHE_LIMIT)
    return chunks


def _clean_topic_candidate(value: str) -> str:
    candidate = re.sub(r"\s+", " ", value or "").strip()
    candidate = re.sub(r"^[\-\*\u2022]+\s*", "", candidate)
    candidate = re.sub(r"^\(?\d+[a-z]?\)?[\.\):-]?\s*", "", candidate)
    candidate = re.sub(
        r"^(week|module|unit|chapter|lesson|topic|lecture|session|class|part|section)\s*\d*[a-z]?\s*[:\-\.)]*\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.split(r"[.;]", candidate, maxsplit=1)[0]
    candidate = TOPIC_VERB_SPLIT_RE.split(candidate, maxsplit=1)[0]
    candidate = candidate.strip(" .:-")
    return candidate[:80]


def _extract_line_topics(source_text: str) -> list[str]:
    topics = []
    seen = set()
    source_lines = []
    source_lines.extend((source_text or "").splitlines())
    source_lines.extend(re.split(r"(?<=[.;])\s+(?=(?:week|module|unit|chapter|lesson|topic|lecture|session|class|part|section)\b)", source_text or "", flags=re.IGNORECASE))

    for raw_line in source_lines:
        line = raw_line.strip()
        if not line:
            continue

        if not _looks_like_outline_line(line):
            continue

        candidate = _clean_topic_candidate(line)
        if not candidate or len(candidate.split()) > 10 or TOPIC_NOISE_RE.search(candidate):
            continue

        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(candidate)
        if len(topics) >= 12:
            break

    return topics


def extract_topics_from_chunks(chunks: list[str], source_text: str = "") -> list[str]:
    """Extract better topic summaries from headings first, then chunk content."""
    topics = _extract_line_topics(source_text)
    seen = {topic.lower() for topic in topics}

    if len(topics) >= 3:
        return topics[:10]

    for chunk in chunks[:15]:
        for sentence in re.split(r"[\n.!?]", chunk):
            candidate = _clean_topic_candidate(sentence)
            if len(candidate) <= 8 or len(candidate.split()) > 10 or TOPIC_NOISE_RE.search(candidate):
                continue
            normalized = candidate.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            topics.append(candidate)
            break
        if len(topics) >= 12:
            break

    return topics[:10]


def _lexical_search_scored(course_id: int, query: str, top_k: int = 5) -> list[tuple[float, str]]:
    from apps.courses.models import CourseMaterial

    normalized_query = _normalized_query(query)
    query_tokens = set(re.findall(r"[a-z0-9]+", normalized_query))
    if not query_tokens:
        return []

    scored_chunks = []
    materials = CourseMaterial.objects.filter(course_id=course_id).only("id", "content_text")
    for material in materials:
        for chunk in _cached_material_chunks(material.id, material.content_text):
            chunk_tokens = set(re.findall(r"[a-z0-9]+", chunk.lower()))
            overlap = len(query_tokens.intersection(chunk_tokens))
            if overlap:
                coverage = overlap / max(len(query_tokens), 1)
                phrase_bonus = 0.3 if normalized_query and normalized_query in chunk.lower() else 0.0
                title_case_bonus = 0.1 if any(token in chunk.lower().splitlines()[0].lower() for token in query_tokens) else 0.0
                scored_chunks.append((round(coverage + phrase_bonus + title_case_bonus, 4), chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return scored_chunks[:top_k]


def _vector_search_scored(course_id: int, query: str, top_k: int = 5) -> list[tuple[float, str]]:
    scored = []
    for collection_name in _get_course_collection_names(course_id):
        collection = _client.get_collection(
            name=collection_name,
            embedding_function=get_embedding_function(),
        )
        if collection.count() == 0:
            continue

        results = collection.query(
            query_texts=[query],
            n_results=min(max(top_k * 2, top_k), collection.count()),
            include=["documents", "distances"],
        )
        documents = (results.get("documents") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        for index, document in enumerate(documents):
            distance = distances[index] if index < len(distances) else 1.0
            try:
                score = 1.0 / (1.0 + float(distance))
            except (TypeError, ValueError):
                score = 0.0
            scored.append((round(score, 4), document))
    return scored


def _hybrid_rank_results(vector_results: list[tuple[float, str]], lexical_results: list[tuple[float, str]], top_k: int) -> list[str]:
    combined_scores = {}
    original_chunks = {}

    for score, chunk in vector_results:
        key = chunk.strip().lower()
        combined_scores[key] = combined_scores.get(key, 0.0) + (score * 0.7)
        original_chunks.setdefault(key, chunk)

    for score, chunk in lexical_results:
        key = chunk.strip().lower()
        combined_scores[key] = combined_scores.get(key, 0.0) + (score * 0.3)
        original_chunks.setdefault(key, chunk)

    ranked = sorted(combined_scores.items(), key=lambda item: item[1], reverse=True)
    return [original_chunks[key] for key, _score in ranked[:top_k]]


def index_course_materials(course_id: int, material_id: int, text: str) -> dict:
    """Chunk text and attempt vector indexing, with offline-safe fallback."""
    logger.info("Indexing material %s for course %s", material_id, course_id)
    chunks = chunk_text(text)
    if not chunks:
        return {"status": "FAILED", "error": "No content to index."}
    _cache_put(
        _lexical_chunk_cache,
        (material_id, _text_signature(text)),
        tuple(chunks),
        LEXICAL_CHUNK_CACHE_LIMIT,
    )
    _invalidate_course_search_cache(course_id)

    topics = extract_topics_from_chunks(chunks, source_text=text)
    result = {
        "status": "SUCCESS",
        "num_chunks": len(chunks),
        "topics": topics,
        "embedding_backend": _embedding_backend or "pending",
    }
    logger.info(
        "Prepared %s chunks and %s extracted topics for material %s",
        len(chunks),
        len(topics),
        material_id,
    )

    try:
        collection = _get_collection(course_id)
        try:
            collection.delete(where={"material_id": material_id})
        except Exception:
            pass

        ids = [f"material_{material_id}_chunk_{index}" for index in range(len(chunks))]
        metadatas = [
            {"course_id": course_id, "material_id": material_id, "chunk_index": index}
            for index in range(len(chunks))
        ]
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        result["embedding_backend"] = _embedding_backend or "chromadb"
        logger.info(
            "Indexed %s chunks for course %s material %s using %s",
            len(chunks),
            course_id,
            material_id,
            result["embedding_backend"],
        )
    except Exception as exc:
        logger.warning(
            "Vector indexing unavailable for course %s material %s. Falling back to "
            "lexical search only: %s",
            course_id,
            material_id,
            exc,
        )
        result["warning"] = "Vector indexing unavailable; lexical fallback enabled."
        result["embedding_backend"] = "lexical-fallback"

    return result


def search_course(course_id: int, query: str, top_k: int = 5) -> list[str]:
    """Search the course store using hybrid semantic + lexical ranking."""
    normalized_query = _normalized_query(query)
    if not normalized_query:
        return []
    cache_key = (course_id, normalized_query, top_k)
    cached = _search_result_cache.get(cache_key)
    if cached is not None:
        _search_result_cache.move_to_end(cache_key)
        return list(cached)

    vector_results = []
    try:
        vector_results = _vector_search_scored(course_id, normalized_query, top_k=top_k)
    except Exception as exc:
        logger.warning("Vector search failed for course %s: %s", course_id, exc)

    lexical_results = _lexical_search_scored(course_id, normalized_query, top_k=max(top_k * 2, top_k))
    hybrid_results = _hybrid_rank_results(vector_results, lexical_results, top_k=top_k)
    if hybrid_results:
        _cache_put(_search_result_cache, cache_key, tuple(hybrid_results), SEARCH_RESULT_CACHE_LIMIT)
        return hybrid_results

    fallback_results = [chunk for _, chunk in lexical_results[:top_k]]
    _cache_put(_search_result_cache, cache_key, tuple(fallback_results), SEARCH_RESULT_CACHE_LIMIT)
    return fallback_results


def delete_material_chunks(course_id: int, material_id: int):
    """Delete stored vector chunks for a material when available."""
    _invalidate_material_cache(course_id, material_id)
    deleted_any = False
    for collection_name in _get_course_collection_names(course_id):
        try:
            collection = _client.get_collection(
                name=collection_name,
                embedding_function=get_embedding_function(),
            )
            collection.delete(where={"material_id": material_id})
            deleted_any = True
        except Exception as exc:
            logger.warning(
                "Skipping vector chunk deletion for material %s in course %s collection %s: %s",
                material_id,
                course_id,
                collection_name,
                exc,
            )

    if deleted_any:
        logger.info(
            "Deleted vector chunks for material %s in course %s",
            material_id,
            course_id,
        )
