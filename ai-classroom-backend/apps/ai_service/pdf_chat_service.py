import logging
import os
import re
from collections import OrderedDict

import chromadb
import pdfplumber
import requests
from django.conf import settings

from apps.chat.models import ChatMessage

logger = logging.getLogger(__name__)

CHROMA_DIR = os.path.join(settings.MEDIA_ROOT, "chromadb")
PDF_CHAT_COLLECTION = "pdf_chat_chunks_v1"
GROQ_EMBED_BASE_URL = getattr(settings, "GROQ_EMBED_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_EMBED_MODEL = getattr(settings, "GROQ_EMBED_MODEL", "")

os.makedirs(CHROMA_DIR, exist_ok=True)

_client = chromadb.PersistentClient(path=CHROMA_DIR)
_embed_session = requests.Session()
_query_cache = OrderedDict()
PDF_CHAT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "define",
    "describe",
    "do",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "its",
    "me",
    "of",
    "on",
    "or",
    "the",
    "their",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _normalize_words(text: str) -> list[str]:
    return re.findall(r"\S+", text or "")


def _chunk_words(words: list[str], chunk_size: int = 500, overlap: int = 100) -> list[str]:
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words).strip()]

    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start += step
    return chunks


def _extract_pdf_pages(pdf_path: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append((idx, text))
    return pages


def _safe_extract_pdf_pages(pdf_path: str) -> list[tuple[int, str]]:
    try:
        return _extract_pdf_pages(pdf_path)
    except Exception as exc:
        logger.warning("PDF page extraction failed for %s: %s", pdf_path, exc)
        return []


def _split_content_text_into_pages(text: str, target_page_count: int | None = None) -> list[tuple[int, str]]:
    normalized = re.sub(r"\r\n?", "\n", (text or "").strip())
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
    if not paragraphs:
        return []

    total_words = sum(len(_normalize_words(paragraph)) for paragraph in paragraphs)
    if total_words == 0:
        return []

    if target_page_count and target_page_count > 1:
        target_words_per_page = max(total_words // target_page_count, 180)
    else:
        target_words_per_page = 650

    pages: list[tuple[int, str]] = []
    current_page: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = len(_normalize_words(paragraph))
        if current_page and current_words + paragraph_words > target_words_per_page:
            pages.append((len(pages) + 1, "\n\n".join(current_page).strip()))
            current_page = []
            current_words = 0

        current_page.append(paragraph)
        current_words += paragraph_words

    if current_page:
        pages.append((len(pages) + 1, "\n\n".join(current_page).strip()))

    return pages


def _material_pages(material) -> tuple[list[tuple[int, str]], str]:
    file_pages: list[tuple[int, str]] = []
    if material.file and os.path.exists(material.file.path):
        file_pages = _safe_extract_pdf_pages(material.file.path)

    content_text = (material.content_text or "").strip()
    content_word_count = len(_normalize_words(content_text))

    if file_pages:
        file_word_count = sum(len(_normalize_words(page_text)) for _, page_text in file_pages)
        if content_word_count > max(file_word_count + 80, int(file_word_count * 1.35)):
            return _split_content_text_into_pages(content_text, target_page_count=len(file_pages)), "content-text-override"
        return file_pages, "pdf-pages"

    if content_text:
        return _split_content_text_into_pages(content_text), "content-text"

    return [], "unavailable"


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not (settings.GROQ_API_KEY or "").strip():
        raise RuntimeError("GROQ_API_KEY is required for PDF chat embeddings.")
    if not (GROQ_EMBED_MODEL or "").strip():
        raise RuntimeError("GROQ_EMBED_MODEL is required for PDF chat embeddings.")
    if not texts:
        return []

    response = _embed_session.post(
        f"{GROQ_EMBED_BASE_URL.rstrip('/')}/embeddings",
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": GROQ_EMBED_MODEL, "input": texts},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json() or {}
    data = payload.get("data") or []
    if not data:
        raise RuntimeError("Groq embeddings response was empty.")
    return [item.get("embedding") or [] for item in data]


def _groq_embed_ready() -> bool:
    return bool((settings.GROQ_API_KEY or "").strip() and (GROQ_EMBED_MODEL or "").strip())


def _collection():
    return _client.get_or_create_collection(name=PDF_CHAT_COLLECTION, metadata={"hnsw:space": "cosine"})


def _cache_set(key, value, limit: int = 256):
    _query_cache[key] = value
    _query_cache.move_to_end(key)
    while len(_query_cache) > limit:
        _query_cache.popitem(last=False)


def _cache_get(key):
    value = _query_cache.get(key)
    if value is not None:
        _query_cache.move_to_end(key)
    return value


def index_material_for_pdf_chat(material) -> dict:
    """Index a course material as page-aware PDF chunks for strict chat retrieval."""
    course_id = material.course_id
    material_id = material.id
    doc_name = material.title or "Uploaded Material"

    pages, page_source = _material_pages(material)

    if not pages:
        return {"status": "FAILED", "error": "No parsable PDF content.", "num_chunks": 0}

    ids = []
    documents = []
    metadatas = []

    for page_number, page_text in pages:
        chunks = _chunk_words(_normalize_words(page_text), chunk_size=500, overlap=100)
        for chunk_idx, chunk in enumerate(chunks):
            ids.append(f"course_{course_id}_material_{material_id}_p{page_number}_c{chunk_idx}")
            documents.append(chunk)
            metadatas.append(
                {
                    "classroom_id": int(course_id),
                    "course_id": int(course_id),
                    "material_id": int(material_id),
                    "doc_name": doc_name,
                    "page_number": int(page_number),
                    "chunk_index": int(chunk_idx),
                }
            )

    if not _groq_embed_ready():
        return {
            "status": "SUCCESS",
            "num_chunks": len(documents),
            "num_pages": len(pages),
            "embedding_backend": "lexical-fallback",
            "page_source": page_source,
            "warning": "GROQ_EMBED_MODEL not configured. Using lexical retrieval fallback.",
        }

    embeddings = _embed_texts(documents)
    if not embeddings or len(embeddings) != len(documents):
        raise RuntimeError("Embedding generation failed for one or more chunks.")

    collection = _collection()
    try:
        collection.delete(where={"material_id": int(material_id)})
    except Exception:
        pass

    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    stale_keys = [key for key in _query_cache if key[0] == int(course_id)]
    for key in stale_keys:
        _query_cache.pop(key, None)

    return {
        "status": "SUCCESS",
        "num_chunks": len(documents),
        "num_pages": len(pages),
        "embedding_backend": f"groq:{GROQ_EMBED_MODEL}",
        "page_source": page_source,
    }


def delete_material_pdf_chat_chunks(course_id: int, material_id: int) -> None:
    collection = _collection()
    collection.delete(where={"material_id": int(material_id)})
    stale_keys = [key for key in _query_cache if key[0] == int(course_id)]
    for key in stale_keys:
        _query_cache.pop(key, None)


def retrieve_pdf_chunks(course_id: int, question: str, top_k: int = 5) -> list[dict]:
    normalized_question = re.sub(r"\s+", " ", (question or "").strip())
    if not normalized_question:
        return []

    cache_key = (int(course_id), normalized_question.lower(), int(top_k))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    retrieved = []

    if _groq_embed_ready():
        try:
            query_embedding = _embed_texts([normalized_question])[0]
            collection = _collection()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=max(int(top_k), 1),
                where={"classroom_id": int(course_id)},
                include=["documents", "metadatas", "distances"],
            )

            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]

            for idx, text in enumerate(documents):
                metadata = metadatas[idx] if idx < len(metadatas) else {}
                distance = distances[idx] if idx < len(distances) else 1.0
                score = 1.0 / (1.0 + float(distance))
                retrieved.append({
                    "text": text,
                    "score": round(score, 4),
                    "doc_name": (metadata or {}).get("doc_name") or "Uploaded Material",
                    "page_number": int((metadata or {}).get("page_number") or 1),
                    "material_id": int((metadata or {}).get("material_id") or 0),
                    "chunk_index": int((metadata or {}).get("chunk_index") or 0),
                })
        except Exception as exc:
            logger.warning("Vector PDF retrieval degraded for course %s: %s", course_id, exc)

    if not retrieved:
        from apps.courses.models import CourseMaterial

        tokens = set(re.findall(r"[a-z0-9]+", normalized_question.lower()))
        if not tokens:
            return []

        scored = []
        materials = CourseMaterial.objects.filter(course_id=course_id).only("id", "title", "file", "content_text")
        for material in materials:
            title = material.title or "Uploaded Material"
            pages, _page_source = _material_pages(material)

            for page_number, page_text in pages:
                chunks = _chunk_words(_normalize_words(page_text), chunk_size=500, overlap=100)
                for chunk_idx, chunk in enumerate(chunks):
                    chunk_tokens = set(re.findall(r"[a-z0-9]+", (chunk or "").lower()))
                    overlap = len(tokens.intersection(chunk_tokens))
                    if overlap == 0:
                        continue
                    score = overlap / max(len(tokens), 1)
                    scored.append(
                        {
                            "text": chunk,
                            "score": round(score, 4),
                            "doc_name": title,
                            "page_number": int(page_number),
                            "material_id": int(material.id),
                            "chunk_index": int(chunk_idx),
                        }
                    )

        scored.sort(key=lambda item: item["score"], reverse=True)
        retrieved = scored[:max(int(top_k), 1)]

    _cache_set(cache_key, retrieved)
    return retrieved


def _format_citations(retrieved_chunks: list[dict]) -> list[dict]:
    citations = []
    seen = set()
    for chunk in retrieved_chunks:
        key = (chunk["doc_name"], chunk["page_number"])
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "doc_name": chunk["doc_name"],
                "page": chunk["page_number"],
                "score": chunk["score"],
                "snippet": (chunk["text"] or "")[:240],
                "type": "citation",
            }
        )
        if len(citations) >= 6:
            break
    return citations


def _looks_like_direct_lookup(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
    if not normalized:
        return False
    direct_prefixes = (
        "what is",
        "who is",
        "when is",
        "where is",
        "define",
        "state",
        "list",
        "what does",
        "what do",
        "which",
    )
    return normalized.startswith(direct_prefixes) or normalized.endswith("?")


def _question_terms(question: str) -> list[str]:
    tokens = []
    seen = set()
    for token in re.findall(r"[a-z0-9]+", (question or "").lower()):
        if len(token) <= 2 or token in PDF_CHAT_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _sentence_candidates(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []

    candidates = []
    seen = set()
    for sentence in re.split(r"(?<=[.!?])\s+", normalized):
        cleaned = sentence.strip(" -")
        if len(cleaned) < 20:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(cleaned)

    if candidates:
        return candidates
    return [normalized]


def _score_passage(question: str, passage: str) -> float:
    question_terms = _question_terms(question)
    if not question_terms:
        return 0.0

    passage_lower = (passage or "").lower()
    passage_tokens = set(re.findall(r"[a-z0-9]+", passage_lower))
    overlap = len(set(question_terms).intersection(passage_tokens))
    if overlap == 0:
        return 0.0

    score = overlap / max(len(set(question_terms)), 1)
    normalized_question = re.sub(r"\s+", " ", (question or "").strip().lower())
    if normalized_question and normalized_question in passage_lower:
        score += 0.4

    subject = _identity_query_subject(question).lower()
    if subject and subject in passage_lower and " is " in passage_lower:
        score += 0.25

    if _looks_like_direct_lookup(question) and " is " in passage_lower:
        score += 0.15

    return round(score, 4)


def _best_passages(question: str, retrieved_chunks: list[dict], limit: int = 3) -> list[dict]:
    ranked = []
    seen = set()
    for chunk in retrieved_chunks:
        for passage in _sentence_candidates(chunk.get("text", "")):
            key = passage.lower()
            if key in seen:
                continue
            seen.add(key)
            score = _score_passage(question, passage)
            if score <= 0:
                continue
            ranked.append(
                {
                    "text": passage,
                    "score": score,
                    "doc_name": chunk["doc_name"],
                    "page_number": chunk["page_number"],
                }
            )

    ranked.sort(key=lambda item: (item["score"], len(item["text"])), reverse=True)
    return ranked[:limit]


def _format_grounded_answer(question: str, passages: list[dict]) -> str:
    if not passages:
        return "I could not find relevant information in this classroom's uploaded PDFs."

    lead = passages[0]
    source_label = f"{lead['doc_name']} page {lead['page_number']}"

    if _looks_like_direct_lookup(question):
        return f"Here is the exact answer text I found in your PDF:\n\n> {lead['text']}\n\nSource: {source_label}."

    if len(passages) == 1:
        return f"{lead['text']}\n\nSource: {source_label}."

    support = []
    for item in passages[1:]:
        if item["score"] < max(lead["score"] * 0.55, 0.18):
            continue
        support.append(f"- {item['text']} ({item['doc_name']} p.{item['page_number']})")
        if len(support) >= 2:
            break

    if not support:
        return f"{lead['text']}\n\nSource: {source_label}."

    return (
        f"{lead['text']}\n\nSupporting details:\n"
        + "\n".join(support)
        + f"\n\nPrimary source: {source_label}."
    )


def _extract_fact_from_chunks(question: str, retrieved_chunks: list[dict]) -> str:
    """Return a deterministic grounded answer for simple fact queries when possible."""
    def _clean_fact_value(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", (value or "")).strip(" .")
        # Trim common worksheet carry-over like "Q)" after a name.
        cleaned = re.split(r"\s+Q\)|\s+Q\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .")
        return cleaned

    q = (question or "").lower()
    fact_key = None
    patterns = [
        ("heroine", [r"\bheroine\b", r"\bfemale lead\b"]),
        ("hero", [r"\bhero\b", r"\bmale lead\b"]),
        ("director", [r"\bdirector\b"]),
    ]
    for key, pats in patterns:
        if any(re.search(pat, q) for pat in pats):
            fact_key = key
            break

    if not fact_key:
        return ""

    for item in retrieved_chunks:
        text = (item.get("text") or "").replace("\n", " ")

        # Pattern 1: "Heroine: Deepika Padukone"
        direct = re.search(rf"\b{re.escape(fact_key)}\b\s*[:\-]\s*([A-Za-z][A-Za-z\s\.']{{1,80}})", text, flags=re.IGNORECASE)
        if direct:
            value = _clean_fact_value(direct.group(1))
            if value:
                return value

        # Pattern 2: "Who is the heroine? A) Deepika Padukone"
        qa = re.search(
            rf"who\s+is\s+the\s+{re.escape(fact_key)}\b.*?\bA\)\s*([A-Za-z][A-Za-z\s\.']{{1,80}})",
            text,
            flags=re.IGNORECASE,
        )
        if qa:
            value = _clean_fact_value(qa.group(1))
            if value:
                return value

    return ""


def _identity_query_subject(question: str) -> str:
    q = (question or "").strip()
    match = re.match(r"^(?:who|what)\s+(?:is|was|are|were)\s+(.+?)(?:\?|\.|$)", q, flags=re.IGNORECASE)
    if not match:
        return ""
    subject = re.sub(r"\s+", " ", match.group(1)).strip(" .?")
    return subject


def _movie_entity_fallback(question: str, retrieved_chunks: list[dict]) -> str:
    return ""


def answer_pdf_chat_question(course, question: str, user=None, top_k: int = 5) -> dict:
    retrieved_chunks = retrieve_pdf_chunks(course.id, question, top_k=top_k)
    if not retrieved_chunks:
        return {
            "answer_text": "I could not find relevant information in this classroom's uploaded PDFs.",
            "sources": [],
        }

    best_passages = _best_passages(question, retrieved_chunks, limit=3)

    identity_subject = _identity_query_subject(question)

    context_block = "\n\n".join(
        [
            f"[Source {idx + 1} | {item['doc_name']} | Page {item['page_number']}]\n{item['text']}"
            for idx, item in enumerate(retrieved_chunks)
        ]
    )

    # Prefer deterministic extraction for simple factual queries.
    extracted_fact = _extract_fact_from_chunks(question, retrieved_chunks)
    if extracted_fact:
        return {
            "answer_text": f"According to the uploaded PDF, the answer is: {extracted_fact}.",
            "sources": _format_citations(retrieved_chunks),
        }

    if best_passages and (_looks_like_direct_lookup(question) or best_passages[0]["score"] >= 0.82):
        return {
            "answer_text": _format_grounded_answer(question, best_passages),
            "sources": _format_citations(retrieved_chunks),
        }

    # For identity questions, keep the evidence visible but let the model answer naturally.
    # If the model is unavailable, we will return a clean PDF-grounded not-found response.

    chat_context = ""
    if user is not None:
        recent_messages = ChatMessage.objects.filter(course=course, student=user).order_by("-timestamp")[:4]
        if recent_messages:
            lines = []
            for message in reversed(recent_messages):
                if message.message:
                    lines.append(f"Student: {message.message[:240]}")
            chat_context = "\n".join(lines)

    prompt = (
        "You are a classroom tutor. Use only the provided PDF evidence. "
        "If evidence is insufficient, state that clearly. "
        "Do not use outside knowledge. Include inline references like [Source 1].\n\n"
        f"Classroom: {course.name}\n"
        f"Recent Chat Context:\n{chat_context or 'None'}\n\n"
        f"Evidence:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    from apps.ai_service.services import call_ollama

    try:
        answer_text = call_ollama(
            prompt,
            format_json=False,
            model=getattr(settings, "GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile"),
            temperature=0.1,
            num_predict=min(getattr(settings, "GROQ_CHAT_MAX_TOKENS", 800), 1200),
        )
    except Exception as exc:
        logger.warning("Groq answer generation failed for course %s: %s", course.id, exc)
        answer_text = ""

    if not (answer_text or "").strip():
        if best_passages:
            answer_text = _format_grounded_answer(question, best_passages)
        elif identity_subject:
            answer_text = f"I couldn't find a direct answer about {identity_subject} in the uploaded PDF."
        else:
            excerpts = []
            for item in retrieved_chunks[:3]:
                snippet = (item.get("text") or "").strip()
                if not snippet:
                    continue
                excerpts.append(f"[{item['doc_name']} p.{item['page_number']}] {snippet[:260]}")
            if excerpts:
                answer_text = "I could not generate a full model answer right now. Here are the most relevant excerpts from your uploaded PDFs:\n\n" + "\n\n".join(excerpts)
            else:
                answer_text = "I could not generate an answer from the provided PDFs right now."

    return {
        "answer_text": (answer_text or "").strip() or "I could not generate an answer from the provided PDFs.",
        "sources": _format_citations(retrieved_chunks),
    }
