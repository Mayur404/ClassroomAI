"""
AI Services — Uses local RAG for context and local Ollama for generation.
"""
import json
import logging
import pdfplumber
import requests

from .rag_service import chunk_text, extract_topics_from_chunks, index_course_materials, search_course

logger = logging.getLogger(__name__)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

def call_ollama(prompt: str, format_json: bool = False) -> str:
    """Helper to query the local Ollama daemon."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }
    if format_json:
        payload["format"] = "json"

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        logger.error(f"Ollama generation failed: {e}")
        raise

def extract_text_from_pdf(pdf_file) -> str:
    """Extracts text from a PDF file using pdfplumber (fully local)."""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += str(extracted) + "\n"
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
    return text


def parse_syllabus_content(syllabus_text: str, course_id: int = 1) -> dict:
    """
    FULLY LOCAL parsing — no AI call initially beyond RAG indexing.
    Chunks the text, stores in ChromaDB.
    """
    try:
        # Index the content in ChromaDB
        result = index_course_materials(course_id, syllabus_text)

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
                "model": "all-MiniLM-L6-v2 (embeddings)",
            },
        }
    except Exception as e:
        logger.error(f"Local parsing failed: {e}")
        return {"status": "FAILED", "error": str(e)}


def generate_schedule_from_course(course) -> list[dict]:
    """Generates a class schedule using local Ollama model."""
    
    # Aggregate topics from ALL materials
    all_topics = []
    seen = set()
    for material in course.materials.all():
        for topic in (material.extracted_topics or []):
            if topic.lower() not in seen:
                seen.add(topic.lower())
                all_topics.append(topic)
    
    # Fallback to course-level topics if no materials
    if not all_topics:
        all_topics = course.extracted_topics or ["General course content"]

    topics_list = ", ".join(all_topics)

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
        response_text = call_ollama(prompt, format_json=True)
        parsed = json.loads(response_text)
        
        # Models sometimes wrap arrays in a dictionary (e.g., {"schedule": [...]})
        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list):
                    return value
            return [parsed]  # Fallback if no list inside
        
        if isinstance(parsed, list):
            return parsed
            
        raise ValueError("Ollama returned an unexpected JSON structure.")
        
    except Exception as e:
        logger.error(f"Ollama schedule generation failed: {e}")
        return [
            {
                "class_number": i + 1,
                "topic": topic,
                "subtopics": ["Overview", "Key concepts"],
                "learning_objectives": [f"Understand {topic}"],
                "duration_minutes": 60,
            }
            for i, topic in enumerate(all_topics)
        ]


def generate_assignment_for_course(course, assignment_type: str, title: str, covered_topics: list[str]) -> dict:
    """Generates an assignment using local Ollama."""
    topics_str = ", ".join(covered_topics)

    prompt = f"""Generate a {assignment_type} assignment for "{course.name}".
Topics covered: {topics_str}
Title: "{title}"

Return JSON with:
- title (string)
- description (string)
- type: "{assignment_type}"
- total_marks (int)
- questions: list of question objects containing:
  - question_number: int
  - prompt: string
  - options: list of strings (populate ONLY if it's an MCQ)
  - marks: int
- rubric: list of {{ "question_number": int, "criteria": [str] }}
- answer_key: for MCQ, {{ "question_number": "correct_option_text" }}"""

    try:
        response_text = call_ollama(prompt, format_json=True)
        parsed = json.loads(response_text)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
        return parsed
    except Exception as e:
        logger.error(f"Ollama assignment generation failed: {e}")
        return {
            "title": title,
            "description": "Error generating AI content offline.",
            "type": assignment_type,
            "total_marks": 0,
            "questions": [],
            "rubric": [],
            "answer_key": {},
        }


def grade_submission(assignment, answers: dict) -> dict:
    """Grades submissions — MCQ locally, open-ended via Ollama."""
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

    prompt = f"""Grade this assignment submission.
Title: {assignment.title}
Rubric: {json.dumps(assignment.rubric)}
Questions: {json.dumps(assignment.questions)}
Answers: {json.dumps(answers)}

Return JSON: {{ "total_score": float, "score_breakdown": [...], "overall_feedback": str }}"""

    try:
        response_text = call_ollama(prompt, format_json=True)
        parsed = json.loads(response_text)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
        return parsed
    except Exception as e:
        logger.error(f"Ollama grading failed: {e}")
        return {"total_score": 0, "overall_feedback": "Grading error: " + str(e)}


def answer_course_question(course, question: str) -> dict:
    """
    RAG pipeline:
    1. Search ChromaDB for relevant chunks (LOCAL)
    2. Send only those chunks + question to Ollama
    """
    relevant_chunks = search_course(course.id, question, top_k=5)
    context_str = "\n---\n".join(relevant_chunks) if relevant_chunks else "No course materials uploaded yet."

    prompt = f"""You are an energetic, supportive AI tutor for the course "{course.name}".
Your goal is to help the student learn. 

If they say hello or general greetings, enthusiastically greet them back and ask how you can help them with "{course.name}".
If they ask a specific question, answer it USING ONLY the provided "RETRIEVED CONTEXT".
If the "RETRIEVED CONTEXT" says "No course materials uploaded yet", politely tell them to upload their syllabus or study materials in the 'Materials' tab so you can help them.
If the answer is truly not in the context, tell them you don't have enough information from the uploaded materials.

Format your response beautifully using Markdown (bolding, lists, code blocks if needed).

RETRIEVED CONTEXT:
{context_str}

STUDENT QUESTION:
{question}
"""

    try:
        response_text = call_ollama(prompt, format_json=False)
        return {
            "answer": response_text,
            "sources": [{"type": "rag_search", "num_chunks": len(relevant_chunks)}],
        }
    except Exception as e:
        logger.error(f"Ollama Q&A failed: {e}")
        return {
            "answer": "I'm having trouble connecting to my local Ollama daemon. Make sure Ollama is running!",
            "sources": [],
        }

