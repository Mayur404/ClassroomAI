import json
import logging
import re
from hashlib import sha256

from apps.ai_service.rag_service import search_course
from apps.ai_service.services import call_ollama
from apps.courses.models import CourseMaterial

logger = logging.getLogger(__name__)


def _fallback_questions(topic: str, chunks: list[str], count: int = 8) -> list[dict]:
    base = [c.strip() for c in chunks if c and c.strip()]
    if not base:
        base = [f"Core concept in {topic}"]

    items = []
    for idx in range(count):
        snippet = base[idx % len(base)][:220]
        items.append(
            {
                "question_text": f"Which statement best matches this lesson point about {topic}?",
                "difficulty": "MEDIUM",
                "options": [
                    {"key": "A", "text": snippet},
                    {"key": "B", "text": f"An unrelated concept outside {topic}"},
                    {"key": "C", "text": "A generic statement not grounded in lesson text"},
                    {"key": "D", "text": "A contradiction of the lesson point"},
                ],
                "correct_option_key": "A",
                "explanation": "The correct option is directly taken from the lesson context.",
                "citation": {"chunk_id": f"fallback-{idx+1}", "source_name": "Lesson Context", "page_or_timestamp": "N/A"},
            }
        )
    return items


def _clean_json(raw: str) -> dict:
    content = (raw or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = re.sub(r"^json\s*", "", content)
    return json.loads(content)


def generate_scoped_mcqs(
    *,
    course_id: int,
    anchor_session_id: int,
    scope_topics: list[str],
    scope_session_ids: list[int],
    module_scope: str,
    count: int = 8,
) -> tuple[list[dict], dict]:
    topics = [str(topic).strip() for topic in (scope_topics or []) if str(topic).strip()]
    if not topics:
        topics = ["General course concepts"]

    topic_query = "; ".join(topics[:8])
    scoped_query = f"Class session topics: {topic_query}. Use only this lesson context."
    chunks = search_course(course_id=course_id, query=scoped_query, top_k=14)

    context = "\n\n".join(chunks[:8])
    if not context:
        materials = CourseMaterial.objects.filter(course_id=course_id).order_by("-created_at")[:5]
        context = "\n\n".join([(m.content_text or "")[:1200] for m in materials if (m.content_text or "").strip()])

    if not context:
        fallback_topic = ", ".join(topics[:3])
        return _fallback_questions(fallback_topic, [], count=count), {
            "session_id": anchor_session_id,
            "session_ids": scope_session_ids,
            "topics": topics,
            "module_scope": module_scope,
            "chunks": [],
            "content_hash": "",
            "strict_context_only": True,
        }

    prompt = f"""
SYSTEM:
You are an assessment generator for an educational platform.
You MUST generate questions strictly from the provided lesson context.
Do NOT use external knowledge.
If context is insufficient, output fewer questions rather than guessing.

CONSTRAINTS:
- Output only valid JSON.
- Every item must be MCQ.
- Exactly 4 options per question.
- Exactly 1 correct option.
- Include explanation grounded in the provided context.
- Include source citation metadata for traceability.

INPUT:
ClassID: {course_id}
AnchorSessionID: {anchor_session_id}
ScopeSessionIDs: {scope_session_ids}
ModuleScope: {module_scope}
Lesson Topics: {topics}

Allowed Context Chunks (ONLY SOURCE OF TRUTH):
{context}

TARGET:
Generate {count} high-quality MCQs reflecting lesson content.

OUTPUT JSON SCHEMA:
{{
  "questions": [
    {{
      "question_text": "string",
      "difficulty": "EASY|MEDIUM|HARD",
      "options": [
        {{"key":"A","text":"string"}},
        {{"key":"B","text":"string"}},
        {{"key":"C","text":"string"}},
        {{"key":"D","text":"string"}}
      ],
      "correct_option_key": "A|B|C|D",
      "explanation": "string",
      "citation": {{
        "chunk_id": "string",
        "source_name": "string",
        "page_or_timestamp": "string"
      }}
    }}
  ]
}}
"""

    questions = []
    try:
        raw = call_ollama(prompt, format_json=True, temperature=0.2, num_predict=1600)
        payload = _clean_json(raw)
        for item in payload.get("questions", []):
            options = item.get("options") or []
            if len(options) != 4:
                continue
            option_keys = {str(opt.get("key", "")).strip().upper() for opt in options}
            if option_keys != {"A", "B", "C", "D"}:
                continue
            correct = str(item.get("correct_option_key", "")).strip().upper()
            if correct not in {"A", "B", "C", "D"}:
                continue
            questions.append(
                {
                    "question_text": str(item.get("question_text", "")).strip(),
                    "difficulty": str(item.get("difficulty", "MEDIUM")).strip().upper() or "MEDIUM",
                    "options": [
                        {"key": str(opt.get("key", "")).strip().upper(), "text": str(opt.get("text", "")).strip()}
                        for opt in options
                    ],
                    "correct_option_key": correct,
                    "explanation": str(item.get("explanation", "")).strip(),
                    "citation": item.get("citation") or {},
                }
            )
    except Exception as exc:
        logger.warning("Quiz generation failed; using fallback: %s", exc)

    if not questions:
        fallback_topic = ", ".join(topics[:3])
        questions = _fallback_questions(fallback_topic, chunks, count=count)

    snapshot = {
        "session_id": anchor_session_id,
        "session_ids": scope_session_ids,
        "topics": topics,
        "module_scope": module_scope,
        "chunks": chunks[:10],
        "content_hash": sha256(context.encode("utf-8")).hexdigest() if context else "",
        "strict_context_only": True,
    }
    return questions[:count], snapshot


def generate_session_mcqs(*, course_id: int, session_id: int, session_topic: str, count: int = 8) -> tuple[list[dict], dict]:
    return generate_scoped_mcqs(
        course_id=course_id,
        anchor_session_id=session_id,
        scope_topics=[session_topic],
        scope_session_ids=[session_id],
        module_scope="single",
        count=count,
    )
