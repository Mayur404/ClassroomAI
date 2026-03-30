"""
AI services with resilient fallbacks and higher-quality course content generation.
"""
from collections import Counter
import json
import logging
import re
import time
from typing import Any

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
import requests
from requests.adapters import HTTPAdapter
from django.conf import settings
from pydantic import ValidationError
from rapidocr_onnxruntime import RapidOCR

from .rag_service import index_course_materials, search_course
from .enhanced_rag import intelligent_search, get_ranked_results, index_material_with_structure
from .answer_generator import AnswerFormatter, classify_and_preprocess
from .schemas import AssignmentResponse, GradingResponse, ScheduleResponse
from .premium_answer_engine import premium_engine, batch_optimizer, perf_monitor

logger = logging.getLogger(__name__)

OLLAMA_API_URL = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
OLLAMA_MODEL = getattr(settings, "OLLAMA_MODEL_PRIMARY", "llama3.2")
OLLAMA_CODER_MODEL = getattr(settings, "OLLAMA_MODEL_CODER", OLLAMA_MODEL)
_ollama_session = requests.Session()
_ollama_session.mount("http://", HTTPAdapter(pool_connections=20, pool_maxsize=20))
_ollama_session.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20))
_OCR_ENGINE = None
OLLAMA_KEEP_ALIVE = getattr(settings, "OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = int(getattr(settings, "OLLAMA_NUM_CTX", 4096))
OLLAMA_CHAT_NUM_PREDICT = int(getattr(settings, "OLLAMA_CHAT_NUM_PREDICT", 320))
PDF_NOISE_RE = re.compile(
    r"^(page\s+\d+(\s+of\s+\d+)?|\d+\s*/\s*\d+|https?://\S+|www\.\S+|copyright\b.*)$",
    re.IGNORECASE,
)
PDF_BULLET_PREFIX_RE = re.compile(r"^[\-\*\u2022\u25aa\u25cf]+\s*")
PDF_LIST_PREFIX_RE = re.compile(r"^(\(?\d+[a-z]?\)?[\.\):-]|[A-Z][\.\)])\s+")

SECTION_PREFIX_RE = re.compile(
    r"^(week|module|unit|chapter|lesson|topic|lecture|session|class|part|section)\s*\d*[a-z]?\s*[:\-\.)]*\s*",
    re.IGNORECASE,
)
NUMBERED_PREFIX_RE = re.compile(r"^\(?\d+[a-z]?\)?[\.\):-]?\s*")
TOPIC_SENTENCE_SPLIT_RE = re.compile(
    r"\s+(?:is|are|covers?|includes?|focuses on|introduces?|explores?|describes?|explains?)\b",
    re.IGNORECASE,
)
CHAT_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
CHAT_FACT_PREFIXES = (
    "what ",
    "when ",
    "where ",
    "who ",
    "which ",
    "define ",
    "state ",
    "mention ",
    "list ",
    "give ",
    "according to ",
    "how many ",
    "how much ",
    "is ",
    "are ",
    "does ",
    "do ",
    "can ",
)
CHAT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "define",
    "did",
    "do",
    "does",
    "for",
    "from",
    "give",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "list",
    "me",
    "mention",
    "of",
    "on",
    "or",
    "please",
    "should",
    "show",
    "state",
    "tell",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _stringify(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text or default
    text = str(value).strip()
    return text or default


def _normalize_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", _stringify(value))


def _normalize_string_list(value: Any, fallback: list[str] | None = None, limit: int | None = None) -> list[str]:
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        source = [value]
    else:
        source = fallback or []

    items = []
    seen = set()
    for item in source:
        text = _normalize_spaces(item).strip(" .:-")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
        if limit and len(items) >= limit:
            break

    if items:
        return items
    return list(fallback or [])


def _unwrap_json_text(response_text: str) -> str:
    cleaned = (response_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def _parse_json_response(response_text: str):
    return json.loads(_unwrap_json_text(response_text))


def _parse_structured_response(response_text: str, schema_model):
    cleaned = _unwrap_json_text(response_text)
    try:
        return schema_model.model_validate_json(cleaned)
    except ValidationError:
        return schema_model.model_validate(json.loads(cleaned))


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clean_topic_label(value: Any) -> str:
    text = _normalize_spaces(value)
    text = re.sub(r"^[\-\*\u2022]+\s*", "", text)
    text = NUMBERED_PREFIX_RE.sub("", text)
    text = SECTION_PREFIX_RE.sub("", text)
    text = re.split(r"[.;]", text, maxsplit=1)[0]
    text = TOPIC_SENTENCE_SPLIT_RE.split(text, maxsplit=1)[0]
    text = text.strip(" .:-")
    return text[:90]


def _looks_like_heading(line: str) -> bool:
    cleaned = _normalize_spaces(line)
    if not cleaned:
        return False

    words = cleaned.split()
    if len(words) > 12:
        return False

    if SECTION_PREFIX_RE.match(cleaned) or NUMBERED_PREFIX_RE.match(cleaned):
        return True

    if cleaned.endswith(":"):
        return True

    if cleaned.isupper() and len(words) <= 8:
        return True

    return len(words) <= 7 and len(cleaned) <= 80 and cleaned.count(".") <= 1


def _split_topic_fragments(value: str, limit: int = 3) -> list[str]:
    parts = re.split(r",|/|;|:| & | and ", value, flags=re.IGNORECASE)
    fragments = _normalize_string_list(parts, limit=limit)
    filtered = [fragment for fragment in fragments if fragment.lower() != value.lower()]
    return filtered[:limit]


def _default_subtopics(topic: str) -> list[str]:
    fragments = _split_topic_fragments(topic, limit=3)
    if len(fragments) >= 2:
        return fragments[:3]

    return [
        f"Key ideas behind {topic}",
        f"Worked examples using {topic}",
        f"Common mistakes with {topic}",
    ]


def _extract_detail_phrases(detail_lines: list[str], topic: str, limit: int = 3) -> list[str]:
    phrases = []
    seen = set()

    for line in detail_lines:
        if _looks_like_heading(line):
            continue
        for clause in re.split(r"[.;]", line):
            for piece in re.split(r",|/|;| and | & ", clause, flags=re.IGNORECASE):
                candidate = _clean_topic_label(piece)
                if not candidate:
                    continue
                if len(candidate.split()) > 8:
                    continue
                key = candidate.lower()
                if key == topic.lower() or key in seen:
                    continue
                seen.add(key)
                phrases.append(candidate)
                if len(phrases) >= limit:
                    return phrases

    return phrases


def _make_learning_objectives(topic: str, subtopics: list[str]) -> list[str]:
    objectives = [f"Explain {topic} clearly and accurately."]
    if subtopics:
        objectives.append(f"Connect {subtopics[0]} back to the main idea of {topic}.")
    if len(subtopics) > 1:
        objectives.append(f"Use {subtopics[-1]} in a simple example or exercise.")
    return objectives[:3]


def _course_topics(course) -> list[str]:
    topics = []
    seen = set()
    for material in course.materials.all():
        for topic in material.extracted_topics or []:
            normalized = _clean_topic_label(topic)
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            topics.append(normalized)

    if topics:
        return topics

    return _normalize_string_list(course.extracted_topics, limit=12)


def _build_schedule_blueprints(course) -> list[dict]:
    cards_by_topic = {}

    def add_topic(topic: str, detail_lines: list[str] | None = None):
        cleaned = _clean_topic_label(topic)
        if not cleaned:
            return
        key = cleaned.lower()
        if key not in cards_by_topic:
            cards_by_topic[key] = {"topic": cleaned, "detail_lines": []}
        if detail_lines:
            cards_by_topic[key]["detail_lines"].extend(
                [_normalize_spaces(line) for line in detail_lines if _normalize_spaces(line)]
            )

    for material in course.materials.all():
        lines = [_normalize_spaces(line) for line in (material.content_text or "").splitlines() if _normalize_spaces(line)]
        current_topic = None
        current_details = []

        for line in lines:
            if _looks_like_heading(line):
                if current_topic:
                    add_topic(current_topic, current_details)
                current_topic = line
                current_details = []
            elif current_topic:
                current_details.append(line)

        if current_topic:
            add_topic(current_topic, current_details)

    for topic in _course_topics(course):
        add_topic(topic)

    blueprints = []
    for card in cards_by_topic.values():
        topic = card["topic"]
        detail_lines = card["detail_lines"]
        subtopics = _extract_detail_phrases(detail_lines, topic)
        if not subtopics:
            subtopics = _default_subtopics(topic)

        blueprints.append(
            {
                "topic": topic,
                "subtopics": subtopics[:3],
                "learning_objectives": _make_learning_objectives(topic, subtopics[:3]),
                "duration_minutes": 75 if len(subtopics) >= 3 else 60,
            }
        )

    return blueprints[:10]


def call_ollama(
    prompt: str,
    format_json: bool = False,
    model: str | None = None,
    temperature: float = 0.2,
    json_schema: dict | None = None,
    num_predict: int | None = None,
    keep_alive: str | None = None,
) -> str:
    """Query the local Ollama daemon."""
    payload = {
        "model": model or OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive or OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }
    if num_predict is not None:
        payload["options"]["num_predict"] = num_predict
    if json_schema:
        payload["format"] = json_schema
    elif format_json:
        payload["format"] = "json"

    response = _ollama_session.post(OLLAMA_API_URL, json=payload, timeout=180)
    response.raise_for_status()
    return response.json().get("response", "")


def _normalize_pdf_line(line: str) -> str:
    normalized = _stringify(line)
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.replace("\uf0b7", "- ")
    normalized = normalized.replace("\u2022", "- ")
    normalized = re.sub(r"[\t\r]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = PDF_BULLET_PREFIX_RE.sub("- ", normalized)
    return normalized.strip()


def _is_pdf_noise_line(line: str) -> bool:
    if not line:
        return True
    if PDF_NOISE_RE.match(line):
        return True
    if re.fullmatch(r"[\d\s\-_/]+", line) and len(line) <= 12:
        return True
    if len(line) == 1 and not re.search(r"[A-Za-z]", line):
        return True
    return False


def _line_starts_new_block(line: str) -> bool:
    return bool(
        _looks_like_heading(line)
        or PDF_LIST_PREFIX_RE.match(line)
        or line.startswith("- ")
    )


def _should_join_pdf_lines(current: str, next_line: str) -> bool:
    if not current or not next_line:
        return False
    if _line_starts_new_block(current) or _line_starts_new_block(next_line):
        return False
    if current.endswith((".", "?", "!", ":", ";")):
        return False
    return bool(re.match(r"^[a-z(]", next_line))


def _merge_pdf_lines(lines: list[str]) -> list[str]:
    merged = []
    buffer = ""

    for raw_line in lines:
        line = _normalize_pdf_line(raw_line)
        if _is_pdf_noise_line(line):
            continue

        if not buffer:
            buffer = line
            continue

        if _should_join_pdf_lines(buffer, line):
            if buffer.endswith("-"):
                buffer = f"{buffer[:-1]}{line}"
            else:
                buffer = f"{buffer} {line}"
            continue

        merged.append(buffer)
        buffer = line

    if buffer:
        merged.append(buffer)

    deduped = []
    previous = ""
    for line in merged:
        if line == previous:
            continue
        deduped.append(line)
        previous = line
    return deduped


def _line_dedupe_key(line: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", line.lower())
    return normalized or line.lower()


def _merge_page_sources(*line_groups: list[str]) -> list[str]:
    merged = []
    seen = set()
    for group in line_groups:
        for raw_line in group:
            line = _normalize_pdf_line(raw_line)
            if _is_pdf_noise_line(line):
                continue
            key = _line_dedupe_key(line)
            if key in seen:
                continue
            seen.add(key)
            merged.append(line)
    return _merge_pdf_lines(merged)


def _extract_pdfium_page_lines(page) -> list[str]:
    text_page = None
    try:
        text_page = page.get_textpage()
        raw_text = text_page.get_text_bounded() or ""
    except Exception:
        raw_text = ""
    finally:
        if text_page is not None:
            text_page.close()

    return _merge_pdf_lines(raw_text.splitlines()) if raw_text else []


def _group_ocr_detections(detections: list[tuple[float, float, str]]) -> list[str]:
    if not detections:
        return []

    lines = []
    current = []
    current_top = None
    for top, left, text in sorted(detections, key=lambda item: (item[0], item[1])):
        if current_top is None or abs(top - current_top) <= 14:
            current.append((left, text))
            current_top = top if current_top is None else current_top
            continue

        lines.append(" ".join(value for _, value in sorted(current)))
        current = [(left, text)]
        current_top = top

    if current:
        lines.append(" ".join(value for _, value in sorted(current)))
    return _merge_pdf_lines(lines)


def _extract_ocr_lines_from_pdfium_page(page, scale: float = 2.0) -> list[str]:
    bitmap = None
    image = None
    try:
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        page_array = np.array(image)
        ocr_engine = _get_ocr_engine()
        ocr_result, _ = ocr_engine(page_array)
    except Exception as exc:
        logger.warning("OCR failed on a PDF page: %s", exc)
        return []
    finally:
        if image is not None:
            image.close()
        if bitmap is not None:
            bitmap.close()

    detections = []
    for item in ocr_result or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        points, text, score = item[0], item[1], item[2]
        normalized_text = _normalize_pdf_line(text)
        if not normalized_text:
            continue
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.45:
            continue
        top = min(point[1] for point in points)
        left = min(point[0] for point in points)
        detections.append((top, left, normalized_text))

    return _group_ocr_detections(detections)


def _page_word_count(page_lines: list[str]) -> int:
    return sum(len(line.split()) for line in page_lines)


def _ocr_render_scale(page_lines: list[str], image_count: int) -> float:
    word_count = _page_word_count(page_lines)
    if word_count == 0 and image_count:
        return 2.25
    if word_count < 25 or image_count >= 3:
        return 2.0
    return 1.8


def _should_run_ocr(page_lines: list[str], image_count: int) -> bool:
    word_count = _page_word_count(page_lines)
    line_count = len(page_lines)

    if word_count == 0:
        return True
    if image_count >= 3 and word_count < 140:
        return True
    if image_count and word_count < 40 and line_count < 4:
        return True
    return word_count < 20 and line_count < 3


def _should_log_pdf_page(page_index: int, total_pages: int) -> bool:
    if total_pages <= 10:
        return True
    return page_index in {1, total_pages} or page_index % 5 == 0


def _log_pdf_page_progress(
    page_index: int,
    total_pages: int,
    *,
    image_count: int,
    used_ocr: bool,
    line_count: int,
):
    if not _should_log_pdf_page(page_index, total_pages):
        return
    percent = round((page_index / max(total_pages, 1)) * 100)
    logger.info(
        "PDF extraction progress %s%% (%s/%s pages) images=%s ocr=%s extracted_lines=%s",
        percent,
        page_index,
        total_pages,
        image_count,
        "yes" if used_ocr else "no",
        line_count,
    )


def _extract_words_as_lines(page) -> list[str]:
    try:
        words = page.extract_words(
            use_text_flow=True,
            keep_blank_chars=False,
            x_tolerance=1,
            y_tolerance=3,
        )
    except Exception:
        return []

    if not words:
        return []

    lines = []
    current_words = []
    current_top = None
    for word in sorted(words, key=lambda item: (round(item["top"], 1), item["x0"])):
        top = float(word["top"])
        if current_top is None or abs(top - current_top) <= 3:
            current_words.append(word["text"])
            current_top = top if current_top is None else current_top
            continue

        lines.append(" ".join(current_words))
        current_words = [word["text"]]
        current_top = top

    if current_words:
        lines.append(" ".join(current_words))
    return lines


def _extract_table_lines(page) -> list[str]:
    lines = []
    try:
        tables = page.extract_tables() or []
    except Exception:
        tables = []

    for table in tables:
        for row in table or []:
            cells = []
            for cell in row or []:
                normalized = _normalize_pdf_line(cell)
                if normalized:
                    cells.append(normalized)
            if cells:
                lines.append(" | ".join(cells))
    return lines


def _should_extract_tables(page, base_lines: list[str]) -> bool:
    word_count = _page_word_count(base_lines)
    if word_count == 0:
        return True

    line_art_count = len(getattr(page, "lines", None) or []) + len(getattr(page, "rects", None) or [])
    return line_art_count >= 8 and (word_count < 180 or len(base_lines) <= 10)


def _extract_page_lines(page) -> list[str]:
    extracted_lines = []
    raw_text = ""
    try:
        raw_text = page.extract_text(layout=True, x_tolerance=1, y_tolerance=3) or ""
    except Exception:
        raw_text = ""

    if raw_text:
        extracted_lines.extend(raw_text.splitlines())

    if len(extracted_lines) < 4:
        extracted_lines = _extract_words_as_lines(page) or extracted_lines

    extracted_lines.extend(_extract_table_lines(page))
    return _merge_pdf_lines(extracted_lines)


def _dedupe_repeated_margin_lines(page_lines: list[list[str]]) -> list[list[str]]:
    if len(page_lines) < 2:
        return page_lines

    edge_counter = Counter()
    for lines in page_lines:
        edges = []
        edges.extend(lines[:2])
        edges.extend(lines[-2:])
        for line in edges:
            edge_counter[line] += 1

    repeated_edges = {
        line for line, count in edge_counter.items()
        if count >= max(2, len(page_lines) // 2)
    }

    cleaned_pages = []
    for lines in page_lines:
        cleaned_pages.append(
            [
                line for index, line in enumerate(lines)
                if line not in repeated_edges or 1 < index < len(lines) - 2
            ]
        )
    return cleaned_pages


def extract_pdf_content(pdf_file) -> dict:
    """Extract cleaner, syllabus-friendly text from a PDF with OCR/image enrichment."""
    result = {
        "text": "",
        "metadata": {
            "page_count": 0,
            "text_page_count": 0,
            "image_page_count": 0,
            "image_count": 0,
            "ocr_page_count": 0,
            "ocr_backend": "rapidocr-onnxruntime",
            "warnings": [],
        },
    }

    started_at = time.perf_counter()
    try:
        logger.info("Starting PDF extraction for %s", pdf_file)
        with pdfplumber.open(pdf_file) as pdf:
            try:
                pdfium_doc = pdfium.PdfDocument(pdf_file)
            except Exception as exc:
                pdfium_doc = None
                result["metadata"]["warnings"].append(f"Fast PDF engine unavailable, falling back to pdfplumber only: {exc}")
            page_text_lines = []
            image_only_pages = 0
            result["metadata"]["page_count"] = len(pdf.pages)
            logger.info("PDF opened successfully with %s pages", result["metadata"]["page_count"])

            try:
                for page_index, page in enumerate(pdf.pages):
                    human_page_index = page_index + 1
                    image_count = len(getattr(page, "images", None) or [])
                    result["metadata"]["image_count"] += image_count
                    if image_count:
                        result["metadata"]["image_page_count"] += 1

                    if pdfium_doc is None:
                        lines = _extract_page_lines(page)
                        if lines:
                            page_text_lines.append(lines)
                            result["metadata"]["text_page_count"] += 1
                        else:
                            page_text_lines.append([])
                            if image_count:
                                image_only_pages += 1
                        _log_pdf_page_progress(
                            human_page_index,
                            result["metadata"]["page_count"],
                            image_count=image_count,
                            used_ocr=False,
                            line_count=len(lines),
                        )
                        continue

                    pdfium_page = pdfium_doc.get_page(page_index)
                    try:
                        pdfium_lines = _extract_pdfium_page_lines(pdfium_page)
                        table_lines = []
                        if _should_extract_tables(page, pdfium_lines):
                            table_lines = _extract_table_lines(page)
                        base_lines = _merge_page_sources(pdfium_lines, table_lines)
                        ocr_lines = []
                        used_ocr = False

                        if _should_run_ocr(base_lines, image_count):
                            ocr_lines = _extract_ocr_lines_from_pdfium_page(
                                pdfium_page,
                                scale=_ocr_render_scale(base_lines, image_count),
                            )
                            if ocr_lines:
                                result["metadata"]["ocr_page_count"] += 1
                            used_ocr = True

                        lines = _merge_page_sources(base_lines, ocr_lines)
                        if not lines:
                            lines = _extract_page_lines(page)

                        if lines:
                            page_text_lines.append(lines)
                            result["metadata"]["text_page_count"] += 1
                        else:
                            page_text_lines.append([])
                            if image_count:
                                image_only_pages += 1
                        _log_pdf_page_progress(
                            human_page_index,
                            result["metadata"]["page_count"],
                            image_count=image_count,
                            used_ocr=used_ocr,
                            line_count=len(lines),
                        )
                    finally:
                        pdfium_page.close()
            finally:
                if pdfium_doc is not None:
                    pdfium_doc.close()

            cleaned_pages = _dedupe_repeated_margin_lines(page_text_lines)
            text = "\n\n".join("\n".join(lines) for lines in cleaned_pages if lines).strip()
            result["text"] = text
            result["metadata"]["word_count"] = len(text.split()) if text else 0

            if not text and image_only_pages:
                result["metadata"]["warnings"].append(
                    "This PDF appears to be image-based or scanned. OCR was attempted but no reliable text was found."
                )
            logger.info(
                "Completed PDF extraction pages=%s text_pages=%s image_pages=%s ocr_pages=%s word_count=%s duration=%.2fs",
                result["metadata"]["page_count"],
                result["metadata"]["text_page_count"],
                result["metadata"]["image_page_count"],
                result["metadata"]["ocr_page_count"],
                result["metadata"]["word_count"],
                time.perf_counter() - started_at,
            )
    except Exception as exc:
        logger.error("Error extracting PDF text: %s", exc)
        result["metadata"]["warnings"].append(str(exc))

    return result


def extract_text_from_pdf(pdf_file) -> str:
    return extract_pdf_content(pdf_file)["text"]


def parse_syllabus_content(syllabus_text: str, course_id: int = 1) -> dict:
    """Chunk and index syllabus content with offline-safe fallbacks."""
    try:
        result = index_course_materials(course_id, course_id, syllabus_text)
        if result["status"] != "SUCCESS":
            return {"status": "FAILED", "error": result.get("error", "Indexing failed")}

        topics = result["topics"]
        return {
            "syllabus_text": syllabus_text,
            "status": "SUCCESS",
            "topics": topics,
            "num_assignments": max(2, len(topics) // 2),
            "assignment_weightage": "20%",
            "policies": [],
            "metadata": {
                "provider": "local_rag",
                "num_chunks": result["num_chunks"],
                "embedding_backend": result.get("embedding_backend"),
            },
        }
    except Exception as exc:
        logger.error("Local parsing failed: %s", exc)
        return {"status": "FAILED", "error": str(exc)}


def extract_course_policies_from_texts(texts: list[str]) -> list[str]:
    policy_lines = []
    seen = set()
    policy_pattern = re.compile(
        r"(attendance|late|deadline|submission|grade|grading|quiz|exam|project|participation|plagiarism|academic integrity|required|must|office hours)",
        re.IGNORECASE,
    )

    for text in texts:
        for raw_line in (text or "").splitlines():
            line = _normalize_spaces(raw_line).strip(" -:")
            if len(line) < 12 or not policy_pattern.search(line):
                continue
            normalized = line[:180]
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            policy_lines.append(normalized)
            if len(policy_lines) >= 8:
                return policy_lines

    return policy_lines


def summarize_course_materials(course) -> dict:
    materials = list(course.materials.all())
    if not materials:
        return {
            "topics": [],
            "policies": [],
            "recommended_num_assignments": 2,
            "assignment_weightage": "25%",
            "schedule_blueprints": [],
            "parse_metadata": {
                "topic_count": 0,
                "policy_count": 0,
                "material_count": 0,
                "schedule_item_count": 0,
                "material_titles": [],
                "topics_preview": [],
            },
        }

    blueprints = _build_schedule_blueprints(course)
    topics = [item["topic"] for item in blueprints] or _course_topics(course)
    policies = extract_course_policies_from_texts([material.content_text for material in materials])
    recommended_assignments = min(6, max(2, (len(topics) + 1) // 2)) if topics else 2
    assignment_weightage = "30%" if recommended_assignments >= 4 else "25%"

    return {
        "topics": topics,
        "policies": policies,
        "recommended_num_assignments": recommended_assignments,
        "assignment_weightage": assignment_weightage,
        "schedule_blueprints": blueprints,
        "parse_metadata": {
            "topic_count": len(topics),
            "policy_count": len(policies),
            "material_count": len(materials),
            "schedule_item_count": len(blueprints),
            "material_titles": [material.title for material in materials[:5]],
            "topics_preview": topics[:5],
        },
    }


def _fallback_schedule(blueprints: list[dict]) -> list[dict]:
    return [
        {
            "class_number": index,
            "topic": item["topic"],
            "subtopics": item["subtopics"],
            "learning_objectives": item["learning_objectives"],
            "duration_minutes": item["duration_minutes"],
        }
        for index, item in enumerate(blueprints, start=1)
    ]


def _normalize_schedule(raw_schedule: Any, blueprints: list[dict]) -> list[dict]:
    if isinstance(raw_schedule, dict):
        raw_schedule = next((value for value in raw_schedule.values() if isinstance(value, list)), [raw_schedule])

    if not isinstance(raw_schedule, list):
        return _fallback_schedule(blueprints)

    normalized_items = []
    seen_topics = set()
    target_count = max(len(blueprints), len(raw_schedule))
    for index in range(1, target_count + 1):
        item = raw_schedule[index - 1] if index - 1 < len(raw_schedule) and isinstance(raw_schedule[index - 1], dict) else {}

        fallback = blueprints[min(index - 1, len(blueprints) - 1)] if blueprints else {
            "topic": f"Lesson {index}",
            "subtopics": [f"Key ideas in lesson {index}"],
            "learning_objectives": [f"Understand lesson {index}."],
            "duration_minutes": 60,
        }
        topic = _clean_topic_label(item.get("topic")) or fallback["topic"]
        topic_key = topic.lower()
        if topic_key in seen_topics and fallback["topic"].lower() not in seen_topics:
            topic = fallback["topic"]
            topic_key = topic.lower()
        seen_topics.add(topic_key)
        subtopics = _normalize_string_list(item.get("subtopics"), fallback=fallback["subtopics"], limit=3)
        learning_objectives = _normalize_string_list(
            item.get("learning_objectives"),
            fallback=fallback["learning_objectives"],
            limit=3,
        )
        normalized_items.append(
            {
                "class_number": index,
                "topic": topic,
                "subtopics": subtopics,
                "learning_objectives": learning_objectives,
                "duration_minutes": _positive_int(item.get("duration_minutes"), fallback["duration_minutes"]),
            }
        )

    return normalized_items or _fallback_schedule(blueprints)


def generate_schedule_from_course(
    course,
    blueprints: list[dict] | None = None,
    *,
    use_ai: bool = True,
) -> list[dict]:
    """Generate a higher-quality class schedule using course structure plus Ollama."""
    blueprints = blueprints or _build_schedule_blueprints(course)
    if not blueprints:
        return []
    if not use_ai:
        return _fallback_schedule(blueprints)

    schedule_schema = ScheduleResponse.model_json_schema()
    prompt = f"""Design a polished class-by-class learning path for the course "{course.name}".

Use this extracted course outline as the source of truth:
{json.dumps(blueprints, ensure_ascii=True)}

Return JSON matching this schema:
{json.dumps(schedule_schema, ensure_ascii=True)}

Example response shape:
{{
  "classes": [
    {{
      "class_number": 1,
      "topic": "{blueprints[0]['topic']}",
      "subtopics": {json.dumps(blueprints[0]['subtopics'], ensure_ascii=True)},
      "learning_objectives": {json.dumps(blueprints[0]['learning_objectives'], ensure_ascii=True)},
      "duration_minutes": {blueprints[0]['duration_minutes']}
    }}
  ]
}}

Requirements:
- Preserve a sensible progression from fundamentals to application.
- Keep every topic concrete and useful. Avoid vague labels like "Overview" as the main topic.
- Keep the same number of classes as the provided outline unless the source outline is clearly redundant.
- Reuse the extracted topics instead of inventing unrelated topics.
- Return only valid JSON.
"""

    try:
        response_text = call_ollama(
            prompt,
            model=OLLAMA_MODEL,
            temperature=0.15,
            json_schema=schedule_schema,
            num_predict=900,
        )
        parsed = _parse_structured_response(response_text, ScheduleResponse)
        return _normalize_schedule(parsed.classes, blueprints)
    except Exception as exc:
        logger.error("Ollama schedule generation failed: %s", exc)
        return _fallback_schedule(blueprints)


def _default_mcq_explanation(topic: str, course_name: str) -> str:
    return f"{topic} is explicitly grounded in the uploaded material for {course_name}, so it is the best answer here."


def _fallback_mcq_options(topic: str, all_topics: list[str]) -> tuple[list[str], str]:
    distractors = [candidate for candidate in all_topics if candidate != topic][:3]
    options = [topic, *distractors]
    fillers = [
        "Only administrative course logistics",
        f"A topic unrelated to {topic}",
        "Not covered in the uploaded material",
    ]
    for filler in fillers:
        if len(options) >= 4:
            break
        if filler not in options:
            options.append(filler)
    return options[:4], topic


def _extract_answer_key_entry(answer_key: dict, question_number: int, fallback_answer: str = "", fallback_explanation: str = "") -> dict:
    entry = answer_key.get(str(question_number), answer_key.get(question_number))
    if isinstance(entry, dict):
        return {
            "correct_option": _stringify(
                entry.get("correct_option") or entry.get("correct_answer") or entry.get("answer"),
                fallback_answer,
            ),
            "explanation": _stringify(entry.get("explanation") or entry.get("why"), fallback_explanation),
        }
    return {
        "correct_option": _stringify(entry, fallback_answer),
        "explanation": fallback_explanation,
    }


def _build_mcq_reasoning(student_answer: str, correct_answer: str, explanation: str, is_correct: bool) -> str:
    correct_answer_text = _stringify(correct_answer, "Not available")
    explanation_text = _stringify(explanation).strip()
    parts = [f"The correct answer is {correct_answer_text}."]
    if explanation_text:
        parts.append(explanation_text)

    student_answer_text = _stringify(student_answer).strip()
    if is_correct:
        parts.append("You got it right because your response matches the correct option.")
    elif student_answer_text:
        parts.append(
            f"You got it wrong because you selected {student_answer_text}, which does not match the correct option."
        )
    else:
        parts.append("You got it wrong because no answer was submitted.")

    return " ".join(parts)


def _assignment_question_target(assignment_type: str, covered_topics: list[str]) -> int:
    if assignment_type == "MCQ":
        return min(6, max(4, len(covered_topics)))
    return min(3, max(2, len(covered_topics)))


def _assignment_outline_excerpt(covered_outline: list[dict] | None, covered_topics: list[str]) -> list[dict]:
    if covered_outline:
        excerpt = []
        for item in covered_outline[:6]:
            if not isinstance(item, dict):
                continue
            excerpt.append(
                {
                    "topic": _clean_topic_label(item.get("topic")),
                    "subtopics": _normalize_string_list(item.get("subtopics"), limit=3),
                    "learning_objectives": _normalize_string_list(item.get("learning_objectives"), limit=3),
                }
            )
        if excerpt:
            return excerpt

    return [{"topic": topic, "subtopics": [], "learning_objectives": []} for topic in covered_topics[:6]]


def _fallback_assignment(course, assignment_type: str, title: str, covered_topics: list[str]) -> dict:
    topics = covered_topics or ["General course content"]
    questions = []
    rubric = []
    answer_key = {}
    target_count = _assignment_question_target(assignment_type, topics)
    topic_sequence = [topics[index % len(topics)] for index in range(target_count)]

    if assignment_type == "MCQ":
        for index, topic in enumerate(topic_sequence, start=1):
            options, correct_answer = _fallback_mcq_options(topic, topics)
            questions.append(
                {
                    "question_number": index,
                    "prompt": f"Which option best matches the key idea of {topic} in {course.name}?",
                    "options": options,
                    "marks": 2,
                }
            )
            rubric.append(
                {
                    "question_number": index,
                    "criteria": ["Award full marks only for the correct option."],
                }
            )
            answer_key[str(index)] = {
                "correct_option": correct_answer,
                "explanation": _default_mcq_explanation(topic, course.name),
            }
    elif assignment_type == "CODING":
        for index, topic in enumerate(topic_sequence, start=1):
            questions.append(
                {
                    "question_number": index,
                    "prompt": (
                        f"Write a small program or function that demonstrates the core idea of "
                        f"{topic} from {course.name}. Include a short explanation of your approach."
                    ),
                    "marks": 10,
                }
            )
            rubric.append(
                {
                    "question_number": index,
                    "criteria": [
                        "Solution is functionally correct.",
                        "Explanation connects code back to the course concept.",
                        "Code handles realistic inputs or edge cases.",
                    ],
                }
            )
    else:
        for index, topic in enumerate(topic_sequence, start=1):
            questions.append(
                {
                    "question_number": index,
                    "prompt": (
                        f"Explain the main idea of {topic} and describe one practical example "
                        f"or application connected to the course."
                    ),
                    "marks": 10,
                }
            )
            rubric.append(
                {
                    "question_number": index,
                    "criteria": [
                        "Shows conceptual understanding.",
                        "Uses a relevant example or application.",
                        "Communicates ideas clearly.",
                    ],
                }
            )

    total_marks = sum(question["marks"] for question in questions)
    description = (
        f"Auto-generated {assignment_type.lower()} assignment for {course.name}. "
        f"Focus areas: {', '.join(topics[:3])}."
    )
    return {
        "title": title,
        "description": description,
        "type": assignment_type,
        "total_marks": total_marks,
        "questions": questions,
        "rubric": rubric,
        "answer_key": answer_key,
    }


def _normalize_assignment_payload(course, assignment_type: str, title: str, covered_topics: list[str], payload: Any) -> dict:
    fallback = _fallback_assignment(course, assignment_type, title, covered_topics)
    if not isinstance(payload, dict):
        return fallback

    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raw_questions = []

    questions = []
    answer_key = payload.get("answer_key") if isinstance(payload.get("answer_key"), dict) else {}
    normalized_answer_key = {}
    target_count = len(fallback["questions"])

    for index in range(1, target_count + 1):
        item = raw_questions[index - 1] if index - 1 < len(raw_questions) and isinstance(raw_questions[index - 1], dict) else {}
        fallback_question = fallback["questions"][min(index - 1, len(fallback["questions"]) - 1)]
        topic_hint = covered_topics[min(index - 1, len(covered_topics) - 1)] if covered_topics else fallback_question["prompt"]
        prompt = _stringify(item.get("prompt") or item.get("question"), fallback_question["prompt"])
        marks = _positive_int(item.get("marks"), fallback_question["marks"])
        question = {
            "question_number": index,
            "prompt": prompt,
            "marks": marks,
        }

        if assignment_type == "MCQ":
            options = _normalize_string_list(item.get("options"), fallback=fallback_question["options"], limit=4)
            if len(options) < 4:
                options = fallback_question["options"]
            fallback_entry = _extract_answer_key_entry(
                fallback["answer_key"],
                index,
                fallback_answer=options[0] if options else "",
                fallback_explanation=_default_mcq_explanation(topic_hint, course.name),
            )
            answer_entry = _extract_answer_key_entry(
                answer_key,
                index,
                fallback_answer=fallback_entry["correct_option"],
                fallback_explanation=fallback_entry["explanation"],
            )
            correct_answer = answer_entry["correct_option"] or fallback_entry["correct_option"]
            explanation = answer_entry["explanation"] or fallback_entry["explanation"]
            if correct_answer and correct_answer not in options:
                options = [correct_answer, *[option for option in options if option != correct_answer]]
            question["options"] = _normalize_string_list(options, fallback=fallback_question["options"], limit=4)
            # Ensure correct_option in answer_key is normalized exactly like options in the list
            normalized_correct_answer = _normalize_spaces(correct_answer or (question["options"][0] if question["options"] else "")).strip(" .:-")
            normalized_answer_key[str(index)] = {
                "correct_option": normalized_correct_answer,
                "explanation": explanation,
            }
        else:
            question["options"] = []

        questions.append(question)

    if not questions:
        return fallback

    rubric = payload.get("rubric") if isinstance(payload.get("rubric"), list) else []
    normalized_rubric = []
    for index, _question in enumerate(questions, start=1):
        raw_entry = rubric[index - 1] if index - 1 < len(rubric) and isinstance(rubric[index - 1], dict) else {}
        default_entry = fallback["rubric"][min(index - 1, len(fallback["rubric"]) - 1)]
        question_level_rubric = raw_questions[index - 1].get("rubric") if index - 1 < len(raw_questions) and isinstance(raw_questions[index - 1], dict) else []
        normalized_rubric.append(
            {
                "question_number": index,
                "criteria": _normalize_string_list(
                    raw_entry.get("criteria") or question_level_rubric,
                    fallback=default_entry["criteria"],
                    limit=4,
                ),
            }
        )

    total_marks = sum(question["marks"] for question in questions)
    return {
        "title": _stringify(payload.get("title"), title),
        "description": _stringify(payload.get("description"), fallback["description"]),
        "type": assignment_type,
        "total_marks": total_marks or fallback["total_marks"],
        "questions": questions,
        "rubric": normalized_rubric,
        "answer_key": normalized_answer_key if assignment_type == "MCQ" else {},
    }


def generate_assignment_for_course(
    course,
    assignment_type: str,
    title: str,
    covered_topics: list[str],
    covered_outline: list[dict] | None = None,
) -> dict:
    """Generate better assignments while preserving robust fallback behavior."""
    covered_topics = covered_topics or _course_topics(course) or ["General course content"]
    chosen_model = OLLAMA_CODER_MODEL if assignment_type == "CODING" else OLLAMA_MODEL
    assignment_schema = AssignmentResponse.model_json_schema()
    outline_excerpt = _assignment_outline_excerpt(covered_outline, covered_topics)
    question_target = _assignment_question_target(assignment_type, covered_topics)
    example_question = {
        "question_number": 1,
        "prompt": f"Explain the main idea of {covered_topics[0]} in {course.name}.",
        "marks": 10 if assignment_type != "MCQ" else 2,
        "options": [
            f"A correct statement about {covered_topics[0]}",
            "A plausible but incorrect alternative",
            "An administrative detail from the course",
            "A topic not covered in the material",
        ] if assignment_type == "MCQ" else [],
        "rubric": [
            "Matches the covered topic accurately.",
            "Uses course-grounded reasoning.",
        ],
    }

    prompt = f"""Create a polished {assignment_type} assignment for "{course.name}".
Only use this covered course outline as the source of truth:
{json.dumps(outline_excerpt, ensure_ascii=True)}
Title: "{title}"

Return JSON matching this schema:
{json.dumps(assignment_schema, ensure_ascii=True)}

Example response shape:
{{
  "title": "{title}",
  "description": "Short teacher-facing summary of what this assignment checks.",
  "type": "{assignment_type}",
  "total_marks": {question_target * (2 if assignment_type == "MCQ" else 10)},
  "questions": [{json.dumps(example_question, ensure_ascii=True)}],
  "rubric": [
    {{
      "question_number": 1,
      "criteria": ["Matches the covered topic accurately.", "Uses course-grounded reasoning."]
    }}
  ],
  "answer_key": {json.dumps({"1": {"correct_option": example_question["options"][0], "explanation": "It is the only option grounded in the covered material."}} if assignment_type == "MCQ" else {}, ensure_ascii=True)}
}}

Quality bar:
- Create exactly {question_target} questions.
- Questions must be concrete, unambiguous, and clearly based on the uploaded course material.
- Avoid filler prompts and avoid repeating the exact same skill in every question.
- For MCQ, use exactly 4 options with plausible distractors based on common confusions.
- For MCQ, every question must have an answer_key entry with correct_option and a short explanation.
- For non-MCQ, keep answer_key as an empty object.
- Keep the assignment challenging but fair for a student who studied the uploaded material.
- Keep the topic progression aligned to the learning path instead of jumping randomly across the syllabus.
- Return only valid JSON.
"""

    try:
        response_text = call_ollama(
            prompt,
            model=chosen_model,
            temperature=0.2 if assignment_type == "MCQ" else 0.15,
            json_schema=assignment_schema,
            num_predict=1400 if assignment_type == "CODING" else 1100,
        )
        parsed = _parse_structured_response(response_text, AssignmentResponse)
        return _normalize_assignment_payload(
            course,
            assignment_type,
            title,
            covered_topics,
            parsed.model_dump(),
        )
    except Exception as exc:
        logger.error("Ollama assignment generation failed: %s", exc)
        return _fallback_assignment(course, assignment_type, title, covered_topics)


def _answer_lookup(answers: dict, question_number: int):
    if not isinstance(answers, dict):
        return ""
    return answers.get(str(question_number), answers.get(question_number, ""))


def _normalized_text(value: Any) -> str:
    import re
    text = _stringify(value).strip().lower().rstrip(".:-")
    return re.sub(r"\s+", " ", text)


def _format_mcq_overall_feedback(total_score: float, total_marks: float, score_breakdown: list[dict]) -> str:
    parts = [f"Score: {total_score}/{total_marks}."]
    for item in score_breakdown[:6]:
        question_number = item.get("question_number")
        student_answer = _stringify(item.get("student_answer"), "No answer")
        correct_answer = _stringify(item.get("correct_answer"), "Not available")
        explanation = _stringify(item.get("explanation"))
        status_text = "Correct." if item.get("is_correct") else f"You chose {student_answer}."
        sentence = f"Q{question_number}: {status_text} Correct option: {correct_answer}."
        if explanation:
            sentence += f" Why: {explanation}"
        parts.append(sentence)
    return " ".join(parts)


def _coerce_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped

    legacy_dict = getattr(value, "dict", None)
    if callable(legacy_dict):
        dumped = legacy_dict()
        if isinstance(dumped, dict):
            return dumped

    return {}


def _normalize_open_ended_score_breakdown(assignment, answers: dict, raw_breakdown: Any) -> list[dict]:
    breakdown_by_number = {}
    if isinstance(raw_breakdown, list):
        for i, entry in enumerate(raw_breakdown):
            entry_dict = _coerce_mapping(entry)
            if not entry_dict:
                continue
            try:
                q_num_raw = entry_dict.get("question_number")
                if q_num_raw is not None:
                    question_number = int(q_num_raw)
                else:
                    question_number = i + 1
            except (TypeError, ValueError):
                question_number = i + 1
            breakdown_by_number[question_number] = entry_dict

    normalized_breakdown = []
    for index, question in enumerate(assignment.questions or [], start=1):
        question_number = int(question.get("question_number", index))
        raw_entry = _coerce_mapping(breakdown_by_number.get(question_number, {}))
        max_score = float(_positive_int(question.get("marks"), 1))
        raw_score = (
            raw_entry.get("score")
            or raw_entry.get("awarded_score")
            or raw_entry.get("marks_awarded")
            or raw_entry.get("points_awarded")
            or 0
        )

        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(score, max_score))

        reasoning = _stringify(
            raw_entry.get("reasoning") or raw_entry.get("feedback") or raw_entry.get("comment"),
            "No detailed reasoning was provided.",
        )
        student_answer = _stringify(
            raw_entry.get("student_answer"),
            _answer_lookup(answers, question_number),
        )

        normalized_breakdown.append(
            {
                "question_number": question_number,
                "score": round(score, 2),
                "max_score": max_score,
                "feedback": reasoning,
                "reasoning": reasoning,
                "student_answer": student_answer,
            }
        )

    return normalized_breakdown


def _keyword_set(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", _normalize_spaces(value).lower())
        if len(token) >= 4 and token not in CHAT_STOPWORDS
    }


def _heuristic_open_ended_result(question: dict, response_text: str) -> tuple[float, str]:
    cleaned_response = _normalize_spaces(response_text)
    word_count = len(re.findall(r"\b\w+\b", cleaned_response))
    if word_count == 0:
        return 0.0, "No answer submitted."

    prompt_keywords = _keyword_set(question.get("prompt"))
    response_keywords = _keyword_set(cleaned_response)
    keyword_overlap = len(prompt_keywords & response_keywords)
    has_example = bool(
        re.search(r"\b(for example|for instance|example|e\.g\.|such as)\b", cleaned_response, re.IGNORECASE)
    )
    multi_sentence = len(re.findall(r"[.!?]", cleaned_response)) >= 2 or "\n" in response_text

    if word_count >= 45:
        score_ratio = 0.9
    elif word_count >= 25:
        score_ratio = 0.82
    elif word_count >= 12:
        score_ratio = 0.72
    elif word_count >= 6:
        score_ratio = 0.58
    else:
        score_ratio = 0.4

    if keyword_overlap >= 2:
        score_ratio += 0.12
    elif keyword_overlap == 1:
        score_ratio += 0.07
    elif prompt_keywords and word_count >= 8:
        score_ratio -= 0.08

    if has_example:
        score_ratio += 0.05
    if multi_sentence and word_count >= 18:
        score_ratio += 0.03

    if keyword_overlap == 0 and word_count < 6:
        score_ratio = min(score_ratio, 0.35)

    score_ratio = max(0.0, min(score_ratio, 1.0))

    if score_ratio >= 0.92:
        feedback = "Strong answer with clear understanding, useful detail, and a relevant example."
    elif score_ratio >= 0.78:
        feedback = "Good answer that shows solid understanding. Add a bit more precision or depth for full marks."
    elif score_ratio >= 0.6:
        feedback = "Reasonable answer with some relevant points. Expand the explanation or example to earn more marks."
    elif score_ratio >= 0.35:
        feedback = "The answer shows some effort, but it needs more course-specific detail and clearer explanation."
    else:
        feedback = "Very limited answer. Add the main concept and at least one clear supporting point or example."

    return round(score_ratio, 4), feedback


def _has_substantive_open_ended_answer(assignment, answers: dict) -> bool:
    for index, question in enumerate(assignment.questions or [], start=1):
        question_number = int(question.get("question_number", index))
        response_text = _stringify(_answer_lookup(answers, question_number))
        if len(re.findall(r"\b\w+\b", response_text)) >= 3:
            return True
    return False


def _should_recover_open_ended_grading(score_breakdown: list[dict], assignment, answers: dict) -> bool:
    if not score_breakdown:
        return True
    if any(float(item.get("score", 0) or 0) > 0 for item in score_breakdown):
        return False
    return _has_substantive_open_ended_answer(assignment, answers)


def _format_open_ended_overall_feedback(total_score: float, total_marks: float, score_breakdown: list[dict]) -> str:
    parts = [f"Score: {round(total_score, 2)}/{total_marks}."]
    for item in score_breakdown[:6]:
        parts.append(
            f"Q{item['question_number']}: {round(item['score'], 2)}/{item['max_score']}. {item['feedback']}"
        )
    return " ".join(parts)


def _fallback_grading(assignment, answers: dict) -> dict:
    total_score = 0.0
    score_breakdown = []

    for index, question in enumerate(assignment.questions or [], start=1):
        question_number = int(question.get("question_number", index))
        max_score = float(_positive_int(question.get("marks"), 1))
        response_text = _stringify(_answer_lookup(answers, question_number))
        score_ratio, feedback = _heuristic_open_ended_result(question, response_text)
        score = round(max_score * score_ratio, 2)

        total_score += score
        score_breakdown.append(
            {
                "question_number": question_number,
                "score": score,
                "max_score": max_score,
                "feedback": feedback,
                "reasoning": feedback,
                "student_answer": response_text,
            }
        )

    overall_feedback = _format_open_ended_overall_feedback(total_score, assignment.total_marks, score_breakdown)
    return {
        "total_score": round(total_score, 2),
        "score_breakdown": score_breakdown,
        "overall_feedback": overall_feedback,
        "ai_feedback": {
            "overall_feedback": overall_feedback,
            "grading_mode": "fallback",
            "answer_review": score_breakdown,
        },
    }


def grade_submission(assignment, answers: dict) -> dict:
    """Grade submissions locally for MCQ, and heuristically if the LLM is unavailable."""
    if assignment.type == "MCQ":
        score_breakdown = []
        total = 0

        for index, question in enumerate(assignment.questions or [], start=1):
            question_number = int(question.get("question_number", index))
            max_score = _positive_int(question.get("marks"), 1)
            answer_entry = _extract_answer_key_entry(
                assignment.answer_key,
                question_number,
                fallback_explanation="This is the option most strongly supported by the uploaded material for this question.",
            )
            correct_answer = answer_entry["correct_option"]
            explanation = answer_entry["explanation"]
            student_answer = _stringify(_answer_lookup(answers, question_number), "")
            correct_norm = _normalized_text(correct_answer)
            student_norm = _normalized_text(student_answer)
            is_correct = bool(correct_norm) and bool(student_norm) and (
                student_norm == correct_norm or 
                student_norm in correct_norm or 
                correct_norm in student_norm
            )
            score = max_score if is_correct else 0
            total += score

            reasoning = _build_mcq_reasoning(student_answer, correct_answer, explanation, is_correct)

            score_breakdown.append(
                {
                    "question_number": question_number,
                    "score": score,
                    "max_score": max_score,
                    "feedback": reasoning,
                    "student_answer": student_answer,
                    "correct_answer": correct_answer,
                    "explanation": explanation,
                    "reasoning": reasoning,
                    "is_correct": is_correct,
                }
            )

        overall_feedback = _format_mcq_overall_feedback(total, assignment.total_marks, score_breakdown)
        return {
            "total_score": total,
            "score_breakdown": score_breakdown,
            "overall_feedback": overall_feedback,
            "ai_feedback": {
                "overall_feedback": overall_feedback,
                "grading_mode": "mcq-auto",
                "answer_review": score_breakdown,
            },
        }

    rubric_by_number = {}
    if isinstance(assignment.rubric, list):
        for index, raw_entry in enumerate(assignment.rubric, start=1):
            entry = _coerce_mapping(raw_entry)
            if not entry:
                continue
            try:
                question_number = int(entry.get("question_number", index))
            except (TypeError, ValueError):
                question_number = index
            rubric_by_number[question_number] = _normalize_string_list(entry.get("criteria"))

    grading_questions = []
    for index, question in enumerate(assignment.questions or [], start=1):
        question_number = int(question.get("question_number", index))
        grading_questions.append(
            {
                "question_number": question_number,
                "prompt": _stringify(question.get("prompt")),
                "max_score": _positive_int(question.get("marks"), 1),
                "criteria": rubric_by_number.get(question_number, []),
            }
        )

    grading_schema = GradingResponse.model_json_schema()
    prompt = f"""Grade this assignment submission.
Title: {assignment.title}
Questions and rubric: {json.dumps(grading_questions)}
Answers: {json.dumps(answers)}

Return JSON matching this schema:
{json.dumps(grading_schema, ensure_ascii=True)}

Requirements:
- Be generous and lenient with grading. Award partial credit generously for effort and relevant keywords.
- Return exactly one score_breakdown item for every question, using the same question_number and max_score.
- Only give 0 marks if the answer is completely blank or clearly unrelated to the question.
- If the student shows partial understanding, usually give them at least 60% to 80% of the marks.
- Reserve scores below 40% for answers that are extremely short, mostly incorrect, or off-topic.
- Use full marks when the answer is clearly relevant, mostly correct, and reasonably complete.
- Keep feedback encouraging, highlight what they did right, and then suggest improvements.
- Do not invent student answers.
- Return only valid JSON.
"""

    try:
        response_text = call_ollama(
            prompt,
            model=OLLAMA_CODER_MODEL if assignment.type == "CODING" else OLLAMA_MODEL,
            temperature=0.1,
            json_schema=grading_schema,
            num_predict=900,
        )
        parsed = _parse_structured_response(response_text, GradingResponse)

        score_breakdown = _normalize_open_ended_score_breakdown(
            assignment,
            answers,
            parsed.score_breakdown,
        )
        if _should_recover_open_ended_grading(score_breakdown, assignment, answers):
            recovered = _fallback_grading(assignment, answers)
            recovered["ai_feedback"]["grading_mode"] = "fallback-recovered"
            return recovered
        total_score = round(sum(item["score"] for item in score_breakdown), 2)
        overall_feedback = _stringify(
            parsed.overall_feedback,
            _format_open_ended_overall_feedback(total_score, assignment.total_marks, score_breakdown),
        )
        return {
            "total_score": total_score,
            "score_breakdown": score_breakdown,
            "overall_feedback": overall_feedback,
            "ai_feedback": {
                "overall_feedback": overall_feedback,
                "grading_mode": "llm",
                "answer_review": score_breakdown,
            },
        }
    except Exception as exc:
        logger.error("Ollama grading failed: %s", exc)
        return _fallback_grading(assignment, answers)


def _chat_fallback_answer(course, question: str, relevant_chunks: list[str]) -> str:
    greeting = _normalized_text(question)
    if greeting in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
        return f"Hello! I am ready to help with {course.name}. Ask me anything from your uploaded materials."

    if not relevant_chunks:
        return (
            "I could not find that in your uploaded materials yet. Add more materials in the "
            "Materials tab and I will use them to answer more accurately."
        )

    excerpts = []
    for chunk in relevant_chunks[:3]:
        trimmed = " ".join(chunk.split())[:260].strip()
        if trimmed:
            excerpts.append(f"- {trimmed}")

    return (
        "I could not reach the local Ollama model right now, but here are the most relevant notes "
        "from your uploaded materials:\n\n" + "\n".join(excerpts)
    )


def _chat_query_terms(question: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", _normalized_text(question))
    seen = set()
    terms = []
    for token in tokens:
        if len(token) <= 2 or token in CHAT_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms[:12]


def _chat_focus_phrase(question: str) -> str:
    cleaned = _normalized_text(question).strip(" ?.")
    cleaned = re.sub(
        r"^(what|when|where|who|which|why|how many|how much|how|define|state|mention|list|give|according to)\s+",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^(is|are|does|do|can|should|could)\s+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _chat_passage_candidates(chunk: str) -> list[str]:
    candidates = []
    seen = set()
    normalized_chunk = re.sub(r"\r\n?", "\n", chunk or "")

    def add_candidate(value: str):
        text = " ".join((value or "").split()).strip()
        if len(text) < 18 or len(text) > 360:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(text)

    for line in normalized_chunk.splitlines():
        add_candidate(line)

    for paragraph in re.split(r"\n{2,}", normalized_chunk):
        add_candidate(paragraph)
        for sentence in CHAT_SENTENCE_SPLIT_RE.split(" ".join(paragraph.split())):
            add_candidate(sentence)

    return candidates


def _score_chat_passage(question: str, passage: str) -> float:
    question_terms = _chat_query_terms(question)
    if not question_terms:
        return 0.0

    passage_terms = set(re.findall(r"[a-z0-9]+", _normalized_text(passage)))
    if not passage_terms:
        return 0.0

    overlap = len(set(question_terms).intersection(passage_terms))
    if overlap == 0:
        return 0.0

    coverage = overlap / max(len(set(question_terms)), 1)
    focus_phrase = _chat_focus_phrase(question)
    focus_bonus = 0.0
    if focus_phrase and focus_phrase in _normalized_text(passage):
        focus_bonus += 0.35
    if overlap == len(set(question_terms)):
        focus_bonus += 0.2
    if len(question_terms) == 1 and question_terms[0] in passage_terms:
        focus_bonus += 0.15

    return round(min(coverage + focus_bonus, 1.5), 4)


def _extract_chat_evidence(question: str, relevant_chunks: list[str], limit: int = 3) -> list[dict]:
    scored_passages = []
    for chunk_index, chunk in enumerate(relevant_chunks):
        for passage in _chat_passage_candidates(chunk):
            score = _score_chat_passage(question, passage)
            if score <= 0:
                continue
            scored_passages.append(
                {
                    "text": passage,
                    "score": score,
                    "chunk_index": chunk_index,
                }
            )

    scored_passages.sort(key=lambda item: (item["score"], -len(item["text"])), reverse=True)
    return scored_passages[:limit]


def _looks_like_fact_lookup(question: str) -> bool:
    cleaned = _normalized_text(question).strip()
    if not cleaned:
        return False
    if any(cleaned.startswith(prefix) for prefix in CHAT_FACT_PREFIXES):
        return True
    return cleaned.endswith("?") and len(cleaned.split()) <= 18


def _format_pdf_grounded_answer(question: str, evidence: list[dict]) -> str:
    if not evidence:
        return "I couldn't find that exact information in the uploaded PDF."

    heading = "Here is the closest wording from your PDF:"
    if _looks_like_fact_lookup(question) and evidence[0]["score"] >= 0.55:
        heading = "Here is the exact answer text I found in your PDF:"
    quotes = "\n".join(f"> {item['text']}" for item in evidence[:2])
    return f"{heading}\n\n{quotes}"


def answer_course_question(course, question: str, user=None, include_context: bool = True) -> dict:
    """Improved question answering with conversation context and intelligent search."""
    
    # Preprocess and classify the question
    prep_info = classify_and_preprocess(question)
    
    # Build conversation context if this is a follow-up question
    context_messages = []
    if include_context and user:
        from apps.chat.models import ChatMessage
        recent_messages = ChatMessage.objects.filter(
            course=course, student=user
        ).order_by('-timestamp')[:6]  # Last 5 messages before current
        
        context_messages = list(reversed(recent_messages))
        
        # Limit context to last ~500 tokens
        context_str = "\n".join([
            f"Q: {m.message}" if m.role == "STUDENT" else f"A: {m.ai_response[:200]}"
            for m in context_messages
        ])
    else:
        context_str = ""
    
    # Try intelligent search first (detects heading queries, etc.)
    search_results = intelligent_search(course.id, question, top_k=8)
    
    # Check if we found exact section matches
    sections_matched = search_results.get("sections_matched", [])
    relevant_chunks = search_results.get("standard_results", [])
    
    # If we have a direct section match for a heading query, use it
    if sections_matched and search_results.get("is_heading_query"):
        section = sections_matched[0]
        formatter = AnswerFormatter()
        
        answer_dict = formatter.format_section_answer(
            question=question,
            section_content=section.get("content_preview", ""),
            section_heading=section.get("heading", ""),
            full_path=section.get("full_path", [])
        )
        
        return {
            "answer": answer_dict["answer"],
            "sources": [
                {
                    "type": "section_direct",
                    "section_heading": answer_dict["section_heading"],
                    "hierarchy": answer_dict["hierarchy"],
                    "material_id": section.get("material_id"),
                }
            ],
        }
    
    # Fall back to evidence-based answer
    if not relevant_chunks:
        relevant_chunks = search_course(course.id, question, top_k=6)
    
    # Extract and score evidence
    evidence = _extract_chat_evidence(question, relevant_chunks, limit=3)
    context_str = "\n---\n".join(relevant_chunks) if relevant_chunks else "No course materials uploaded yet."
    evidence_str = "\n".join(
        f"[{index}] {item['text']}"
        for index, item in enumerate(evidence, start=1)
    ) or "None"

    # For factual questions with good evidence, use direct grounding
    if _looks_like_fact_lookup(question) and evidence and evidence[0]["score"] >= 0.55:
        return {
            "answer": _format_pdf_grounded_answer(question, evidence),
            "sources": [
                {"type": "rag_search", "num_chunks": len(relevant_chunks)},
                *[
                    {
                        "type": "references",
                        "snippet": item["text"],
                        "score": item["score"],
                        "chunk_index": item["chunk_index"],
                    }
                    for item in evidence
                ],
            ],
        }

    # Use optimized prompt based on question type with conversation context
    question_type = prep_info.get("question_type", "general")
    answer_length = prep_info.get("estimated_answer_length", 250)
    
    # Enhanced prompt with context
    conversation_context_section = ""
    if context_messages:
        conversation_context_section = f"""
CONVERSATION HISTORY (for context):
{chr(10).join([f"- {m.message if m.role == 'STUDENT' else m.ai_response[:150]}" for m in context_messages[:3]])}

Remember the previous discussion when answering this follow-up question.
"""
    
    prompt = f"""You are a retrieval-only AI tutor for the course "{course.name}".
Your job is to answer using only the uploaded PDF evidence below.
Answer type: {question_type.upper()}
Expected length: {answer_length} characters.

{conversation_context_section}

CRITICAL RULES:
1. Answer ONLY from the provided EVIDENCE and CONTEXT.
2. Never add outside knowledge or generic explanations.
3. Stay as close as possible to the PDF wording.
4. If you can find an exact match or section reference, mention it.
5. If the answer isn't in the materials, say: "I couldn't find that exact information in the course materials."
6. Be concise but complete for the question type.
7. For section/heading queries, mention where in the course it's found.
8. Remember and reference previous parts of the conversation if this is a follow-up.

EVIDENCE QUOTES:
{evidence_str}

RETRIEVED CONTEXT:
{context_str}

STUDENT QUESTION:
{question}

ANSWER:"""

    try:
        response_text = call_ollama(
            prompt,
            format_json=False,
            model=OLLAMA_MODEL,
            temperature=0.05,
            num_predict=OLLAMA_CHAT_NUM_PREDICT,
        )
        return {
            "answer": response_text,
            "sources": [
                {"type": "rag_search", "num_chunks": len(relevant_chunks)},
                *[
                    {
                        "type": "references",
                        "snippet": item["text"],
                        "score": item["score"],
                        "chunk_index": item["chunk_index"],
                    }
                    for item in evidence
                ],
            ],
        }
    except Exception as exc:
        logger.error("Ollama Q&A failed: %s", exc)
        return {
            "answer": _format_pdf_grounded_answer(question, evidence) if evidence else _chat_fallback_answer(course, question, relevant_chunks),
            "sources": [
                {"type": "rag_search", "num_chunks": len(relevant_chunks)},
                *[
                    {
                        "type": "references",
                        "snippet": item["text"],
                        "score": item["score"],
                        "chunk_index": item["chunk_index"],
                    }
                    for item in evidence
                ],
            ],
        }


# ============ PREMIUM ANSWER GENERATION (NEW) ============


def answer_course_question_premium(
    course,
    question: str,
    user=None,
    include_context: bool = True,
    use_cache: bool = True,
) -> dict:
    """
    Premium answer generation with all enhancements:
    - Better PDF extraction (scanned + native)
    - Perfect source attribution
    - Reliable prompting (non-random answers)
    - Better semantic search
    - Response validation
    
    This is the recommended function for new code.
    Falls back to answer_course_question if issues occur.
    """
    
    try:
        # Check cache
        if use_cache and batch_optimizer.should_use_cached_answer(question, course.id):
            cached = batch_optimizer.get_cached_answer(question, course.id)
            if cached:
                logger.info("Using cached answer")
                return cached
        
        # Build conversation history if needed
        conversation_history = None
        if include_context and user:
            from apps.chat.models import ChatMessage
            recent_messages = ChatMessage.objects.filter(
                course=course, student=user
            ).order_by('-timestamp')[:6]
            
            conversation_history = []
            for msg in reversed(recent_messages):
                if msg.role == "STUDENT":
                    conversation_history.append(msg.message[:100])
                else:
                    conversation_history.append(msg.ai_response[:150])
        
        # Create search function wrapper
        def search_wrapper(query, top_k=10):
            """Wrapper around search_course function."""
            try:
                results = search_course(course.id, query, top_k=top_k)
                # Convert to (text, score) tuples
                return [(r, 0.8) for r in results] if results else []
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
        
        # Create LLM function wrapper
        def llm_wrapper(prompt):
            """Wrapper around Ollama."""
            try:
                return call_ollama(
                    prompt,
                    format_json=False,
                    model=OLLAMA_MODEL,
                    temperature=0.05,
                    num_predict=OLLAMA_CHAT_NUM_PREDICT,
                )
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                return None
        
        # Generate premium answer
        response = premium_engine.answer_question_premium(
            question=question,
            course=course,
            user=user,
            search_func=search_wrapper,
            llm_func=llm_wrapper,
            conversation_history=conversation_history,
        )
        
        # Cache answer
        batch_optimizer.cache_answer(question, course.id, response)
        
        # Log metrics
        perf_monitor.log_answer(
            processing_time_ms=response["metadata"]["processing_time_ms"],
            confidence=response["confidence"],
            evidence_count=response["metadata"]["evidence_count"],
            is_cached=False,
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Premium answer generation failed: {e}. Falling back to standard.")
        # Fallback to original function
        return answer_course_question(course, question, user, include_context)
