import logging
import os
import re
from collections import OrderedDict
from difflib import SequenceMatcher

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
_answer_cache = OrderedDict()
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
PDF_CHAT_CONTRAST_PAIRS = (
    ("before", "after", 0.34),
    ("after", "before", 0.34),
    ("hero", "heroine", 0.42),
    ("heroine", "hero", 0.42),
    ("male", "female", 0.26),
    ("female", "male", 0.26),
    ("first", "second", 0.18),
    ("second", "first", 0.18),
)


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


def _answer_cache_set(key, value, limit: int = 256):
    _answer_cache[key] = value
    _answer_cache.move_to_end(key)
    while len(_answer_cache) > limit:
        _answer_cache.popitem(last=False)


def _answer_cache_get(key):
    value = _answer_cache.get(key)
    if value is not None:
        _answer_cache.move_to_end(key)
    return value


def _invalidate_course_caches(course_id: int) -> None:
    stale_query_keys = [key for key in _query_cache if key[0] == int(course_id)]
    for key in stale_query_keys:
        _query_cache.pop(key, None)

    stale_answer_keys = [key for key in _answer_cache if key[0] == int(course_id)]
    for key in stale_answer_keys:
        _answer_cache.pop(key, None)


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

    _invalidate_course_caches(course_id)

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
    _invalidate_course_caches(course_id)


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


def _normalized_chat_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _question_bigrams(question: str) -> set[tuple[str, str]]:
    terms = _question_terms(question)
    return {(terms[index], terms[index + 1]) for index in range(len(terms) - 1)}


def _contrast_penalty(question_terms: set[str], candidate_terms: set[str]) -> float:
    penalty = 0.0
    for expected, conflicting, weight in PDF_CHAT_CONTRAST_PAIRS:
        if expected in question_terms and conflicting in candidate_terms and expected not in candidate_terms:
            penalty += weight
    return penalty


def _score_text_alignment(question: str, candidate_text: str, *, base_score: float = 0.0) -> float:
    normalized_question = _normalized_chat_text(question)
    normalized_candidate = _normalized_chat_text(candidate_text)
    if not normalized_question or not normalized_candidate:
        return 0.0

    question_terms = set(_question_terms(question))
    candidate_terms = set(_question_terms(candidate_text))
    if not question_terms or not candidate_terms:
        return 0.0

    overlap = len(question_terms.intersection(candidate_terms))
    if overlap == 0:
        return 0.0

    token_recall = overlap / max(len(question_terms), 1)
    token_precision = overlap / max(len(candidate_terms), 1)

    question_bigrams = _question_bigrams(question)
    candidate_bigrams = _question_bigrams(candidate_text)
    bigram_overlap = 0.0
    if question_bigrams and candidate_bigrams:
        bigram_overlap = len(question_bigrams.intersection(candidate_bigrams)) / max(len(question_bigrams), 1)

    ratio = SequenceMatcher(None, normalized_question, normalized_candidate).ratio()

    score = (token_recall * 0.52) + (token_precision * 0.1) + (bigram_overlap * 0.23) + (ratio * 0.15)
    if normalized_question == normalized_candidate:
        score += 0.28
    elif normalized_question in normalized_candidate or normalized_candidate in normalized_question:
        score += 0.12

    score += min(max(float(base_score), 0.0), 1.0) * 0.08
    score -= _contrast_penalty(question_terms, candidate_terms)
    return round(max(score, 0.0), 4)


def _clean_structured_answer(answer_text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (answer_text or "")).strip(" .")
    cleaned = re.split(
        r"\s+(?:Q(?:uestion)?|A(?:nswer)?)\s*[:\)\.\-]",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" .")
    return cleaned


def _extract_inline_qa_pairs(text: str) -> list[tuple[str, str]]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []

    pattern = re.compile(
        r"(?:^|\s)(?:Q|Question)\s*[:\)\.\-]\s*(?P<question>.+?)\s+"
        r"(?:A|Answer)\s*[:\)\.\-]\s*(?P<answer>.+?)(?=(?:\s+(?:Q|Question)\s*[:\)\.\-])|$)",
        flags=re.IGNORECASE,
    )

    pairs = []
    seen = set()
    for match in pattern.finditer(normalized):
        prompt = re.sub(r"\s+", " ", (match.group("question") or "")).strip(" .")
        answer = _clean_structured_answer(match.group("answer") or "")
        if not prompt or not answer:
            continue
        key = (prompt.lower(), answer.lower())
        if key in seen:
            continue
        seen.add(key)
        pairs.append((prompt, answer))
    return pairs


def _extract_label_value_pairs(text: str) -> list[tuple[str, str]]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []

    pattern = re.compile(
        r"(?P<label>[A-Z][A-Za-z][A-Za-z\s]{0,30}?)\s*:\s*(?P<value>.+?)(?=(?:\s+[A-Z][A-Za-z][A-Za-z\s]{0,30}?\s*:)|$)"
    )

    pairs = []
    seen = set()
    for match in pattern.finditer(normalized):
        label = re.sub(r"\s+", " ", (match.group("label") or "")).strip(" .:-")
        value = _clean_structured_answer(match.group("value") or "")
        if not label or not value:
            continue
        if len(label.split()) > 4 or len(value.split()) > 18:
            continue
        key = (label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        pairs.append((label, value))
    return pairs


def _best_structured_matches(question: str, retrieved_chunks: list[dict], limit: int = 3) -> list[dict]:
    candidates = []
    seen = set()

    for chunk in retrieved_chunks:
        chunk_text = chunk.get("text") or ""
        base_score = float(chunk.get("score") or 0.0)

        for prompt_text, answer_text in _extract_inline_qa_pairs(chunk_text):
            prompt_score = _score_text_alignment(question, prompt_text, base_score=base_score)
            answer_score = _score_text_alignment(question, answer_text, base_score=base_score)
            combined_score = max(prompt_score, answer_score * 0.7, min(prompt_score + (answer_score * 0.18), 1.4))
            if combined_score <= 0:
                continue

            key = (prompt_text.lower(), answer_text.lower(), chunk["doc_name"], int(chunk["page_number"]))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "kind": "qa",
                    "score": round(combined_score, 4),
                    "question_text": prompt_text,
                    "answer_text": answer_text,
                    "evidence_text": f"Q: {prompt_text} A: {answer_text}",
                    "doc_name": chunk["doc_name"],
                    "page_number": chunk["page_number"],
                }
            )

        for label, value in _extract_label_value_pairs(chunk_text):
            label_prompt = f"What is the {label}?"
            score = max(
                _score_text_alignment(question, label_prompt, base_score=base_score),
                _score_text_alignment(question, f"{label} {value}", base_score=base_score) * 0.9,
            )
            if score <= 0:
                continue

            key = (label.lower(), value.lower(), chunk["doc_name"], int(chunk["page_number"]))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "kind": "label",
                    "score": round(score, 4),
                    "question_text": label_prompt,
                    "answer_text": value,
                    "evidence_text": f"{label}: {value}",
                    "doc_name": chunk["doc_name"],
                    "page_number": chunk["page_number"],
                }
            )

    candidates.sort(key=lambda item: (item["score"], len(item["answer_text"])), reverse=True)
    return candidates[:limit]


def _is_confident_structured_match(matches: list[dict]) -> bool:
    if not matches:
        return False
    lead_score = matches[0]["score"]
    runner_up = matches[1]["score"] if len(matches) > 1 else 0.0
    return lead_score >= 0.62 or (lead_score >= 0.48 and (lead_score - runner_up) >= 0.12)


def _format_structured_answer(answer_text: str, doc_name: str, page_number: int) -> str:
    cleaned = _clean_structured_answer(answer_text)
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return f"{cleaned}\n\nSource: {doc_name} page {page_number}."


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


def _concise_sentence(text: str, max_words: int = 28) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return ""
    words = normalized.split()
    if len(words) <= max_words:
        return normalized
    shortened = " ".join(words[:max_words]).rstrip(" ,;:")
    if not shortened.endswith((".", "!", "?")):
        shortened += "..."
    return shortened


def _needs_llm_synthesis(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
    synthesis_markers = (
        "why ",
        "how ",
        "compare",
        "difference",
        "advantages",
        "disadvantages",
        "steps",
        "process",
        "summarize",
        "briefly explain",
        "explain why",
        "explain how",
        "relationship",
        "impact",
    )
    return any(marker in normalized for marker in synthesis_markers)


def _format_fast_concise_answer(question: str, passages: list[dict]) -> str:
    if not passages:
        return "I could not find relevant information in this classroom's uploaded PDFs."

    lead = passages[0]
    lead_text = _concise_sentence(lead["text"], max_words=32)
    if _looks_like_direct_lookup(question):
        return (
            "Here is the exact answer text I found in your PDF:\n\n"
            f"> {lead_text}\n\n"
            f"Source: {lead['doc_name']} page {lead['page_number']}."
        )

    support_lines = []
    for item in passages[1:]:
        if item["score"] < max(lead["score"] * 0.6, 0.2):
            continue
        support_lines.append(_concise_sentence(item["text"], max_words=20))
        if len(support_lines) >= 2:
            break

    if not support_lines:
        return f"{lead_text}\n\nSource: {lead['doc_name']} page {lead['page_number']}."

    return (
        f"{lead_text}\n\n"
        + "Key point: "
        + " ".join(support_lines)
        + f"\n\nSource: {lead['doc_name']} page {lead['page_number']}."
    )


def _prompt_evidence_block(passages: list[dict], limit: int = 2) -> str:
    selected = passages[:limit]
    return "\n\n".join(
        f"[Evidence {index}] {item['doc_name']} p.{item['page_number']}: {item.get('evidence_text') or item.get('text') or item.get('answer_text') or ''}"
        for index, item in enumerate(selected, start=1)
    )


def _finalize_llm_answer(answer_text: str, fallback_passages: list[dict]) -> str:
    cleaned = re.sub(r"\s+\n", "\n", (answer_text or "").strip())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if not cleaned:
        return _format_fast_concise_answer("", fallback_passages)

    words = cleaned.split()
    if len(words) > 120:
        cleaned = " ".join(words[:120]).rstrip(" ,;:")
        if not cleaned.endswith((".", "!", "?")):
            cleaned += "..."

    return cleaned


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
    normalized_question = re.sub(r"\s+", " ", (question or "").strip())
    if not normalized_question:
        return {
            "answer_text": "Question cannot be empty.",
            "sources": [],
        }

    answer_cache_key = (int(course.id), normalized_question.lower(), int(top_k))
    cached_answer = _answer_cache_get(answer_cache_key)
    if cached_answer is not None:
        return cached_answer

    retrieved_chunks = retrieve_pdf_chunks(course.id, question, top_k=int(top_k))
    if not retrieved_chunks:
        result = {
            "answer_text": "I could not find relevant information in this classroom's uploaded PDFs.",
            "sources": [],
        }
        _answer_cache_set(answer_cache_key, result)
        return result

    context_block = "\n\n".join(
        [
            f"[Source {idx + 1}] {item['doc_name']} (page {item['page_number']})\n{item['text']}"
            for idx, item in enumerate(retrieved_chunks)
        ]
    )

    prompt = (
        "Answer only from the provided course material. Do not answer from general knowledge.\n\n"
        f"Course material context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "If the answer is not in the provided context, say that the material does not contain it."
    )

    from apps.ai_service.services import call_ollama

    try:
        answer_text = call_ollama(
            prompt,
            format_json=False,
            model=getattr(settings, "GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile"),
            temperature=0.2,
            num_predict=min(getattr(settings, "GROQ_CHAT_MAX_TOKENS", 800), 800),
        )
    except Exception as exc:
        logger.warning("Groq answer generation failed for course %s: %s", course.id, exc)
        answer_text = ""

    if not (answer_text or "").strip():
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

    result = {
        "answer_text": (answer_text or "").strip() or "I could not generate an answer from the provided PDFs.",
        "sources": _format_citations(retrieved_chunks),
    }
    _answer_cache_set(answer_cache_key, result)
    return result
