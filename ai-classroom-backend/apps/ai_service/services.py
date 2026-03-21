"""
AI Services — Uses local RAG for context, Gemini only for generation.
"""
import json
import logging
import pdfplumber
from django.conf import settings
from google import genai

from .rag_service import chunk_text, extract_topics_from_chunks, index_course_materials, search_course

logger = logging.getLogger(__name__)

# Initialize Gemini Client
client = genai.Client(api_key=settings.GEMINI_API_KEY)


def get_model_name(is_coder=False):
    return settings.GEMINI_MODEL_CODER if is_coder else settings.GEMINI_MODEL_PRIMARY


def extract_text_from_pdf(pdf_file) -> str:
    """Extracts text from a PDF file using pdfplumber (fully local)."""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
    return text


def parse_syllabus_content(syllabus_text: str, course_id: int = 1) -> dict:
    """
    FULLY LOCAL parsing — no Gemini call.
    Chunks the text, stores in ChromaDB, extracts topics from content.
    """
    try:
        # Index the content in ChromaDB
        result = index_course_materials(course_id, syllabus_text)

        if result["status"] != "SUCCESS":
            return {"status": "FAILED", "error": result.get("error", "Indexing failed")}

        topics = result["topics"]
        chunks = chunk_text(syllabus_text)

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
                "model": "all-MiniLM-L6-v2 (embeddings)",
            },
        }
    except Exception as e:
        logger.error(f"Local parsing failed: {e}")
        return {"status": "FAILED", "error": str(e)}


def generate_schedule_from_course(course) -> list[dict]:
    """Generates a class schedule using Gemini with minimal context (just topics)."""
    model_id = get_model_name()
    topics_list = ", ".join(course.extracted_topics or ["General course content"])

    prompt = f"""Create a class-by-class learning schedule for a course named "{course.name}".
Main Topics: {topics_list}

Return a JSON array where each object has:
- class_number (int)
- topic (string)
- subtopics (list of 2-3 strings)
- learning_objectives (list of 2-3 strings)
- duration_minutes (int, e.g. 60)

Provide 5-10 classes to cover all topics."""

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini schedule generation failed: {e}")
        return [
            {
                "class_number": i + 1,
                "topic": topic,
                "subtopics": ["Overview", "Key concepts"],
                "learning_objectives": [f"Understand {topic}"],
                "duration_minutes": 60,
            }
            for i, topic in enumerate(course.extracted_topics or ["Introduction"])
        ]


def generate_assignment_for_course(course, assignment_type: str, title: str, covered_topics: list[str]) -> dict:
    """Generates an assignment using Gemini with topic context only."""
    model_id = get_model_name()
    topics_str = ", ".join(covered_topics)

    prompt = f"""Generate a {assignment_type} assignment for "{course.name}".
Topics covered: {topics_str}
Title: "{title}"

Return JSON with:
- title (string)
- description (string)
- type: "{assignment_type}"
- total_marks (int)
- questions: list of question objects
  - MCQ: {{ "question_number": int, "prompt": str, "options": [str], "marks": int }}
  - ESSAY: {{ "question_number": int, "prompt": str, "marks": int, "constraints": [str] }}
- rubric: list of {{ "question_number": int, "criteria": [str] }}
- answer_key: for MCQ, {{ "question_number": "correct_option_text" }}"""

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini assignment generation failed: {e}")
        return {
            "title": title,
            "description": "Error generating AI content.",
            "type": assignment_type,
            "total_marks": 0,
            "questions": [],
            "rubric": [],
            "answer_key": {},
        }


def grade_submission(assignment, answers: dict) -> dict:
    """Grades submissions — MCQ locally, open-ended via Gemini."""
    if assignment.type == "MCQ":
        score_breakdown = []
        total = 0
        for question in assignment.questions:
            qn = str(question["question_number"])
            correct = assignment.answer_key.get(qn)
            student_answer = answers.get(qn)
            score = question["marks"] if student_answer == correct else 0
            total += score
            score_breakdown.append({
                "question_number": question["question_number"],
                "score": score,
                "max_score": question["marks"],
                "feedback": "Correct" if score else f"Incorrect. Correct answer: {correct}",
            })
        return {
            "total_score": total,
            "score_breakdown": score_breakdown,
            "overall_feedback": "MCQ automated grading finished.",
        }

    model_id = get_model_name()
    prompt = f"""Grade this assignment submission.
Title: {assignment.title}
Rubric: {json.dumps(assignment.rubric)}
Questions: {json.dumps(assignment.questions)}
Answers: {json.dumps(answers)}

Return JSON: {{ "total_score": float, "score_breakdown": [...], "overall_feedback": str }}"""

    try:
        response = client.models.generate_content(
            model=model_id, contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini grading failed: {e}")
        return {"total_score": 0, "overall_feedback": "Grading error: " + str(e)}


def answer_course_question(course, question: str) -> dict:
    """
    RAG pipeline:
    1. Search ChromaDB for relevant chunks (LOCAL)
    2. Send only those chunks + question to Gemini
    """
    # Step 1: Local vector search
    relevant_chunks = search_course(course.id, question, top_k=5)

    if not relevant_chunks:
        return {
            "answer": "I don't have any study materials to reference yet. Please upload a PDF first!",
            "sources": [],
        }

    # Step 2: Build context from retrieved chunks
    context = "\n---\n".join(relevant_chunks)

    # Step 3: Send minimal prompt to Gemini
    model_id = get_model_name()
    prompt = f"""You are an AI tutor for "{course.name}".
Answer the student's question using ONLY the following retrieved context from their study materials.
If the answer isn't in the context, say you don't have enough information.

RETRIEVED CONTEXT:
{context}

STUDENT QUESTION:
{question}

Give a clear, helpful, and educational answer."""

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
        )
        return {
            "answer": response.text,
            "sources": [{"type": "rag_search", "num_chunks": len(relevant_chunks)}],
        }
    except Exception as e:
        logger.error(f"Gemini Q&A failed: {e}")
        return {
            "answer": "I'm having trouble connecting to the AI. Please try again in a moment.",
            "sources": [],
        }
