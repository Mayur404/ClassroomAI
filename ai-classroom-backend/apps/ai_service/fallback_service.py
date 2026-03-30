"""
Fallback answers and graceful degradation when LLM service is unavailable.
Provides basic retrieval-based answers without LLM when Ollama is down.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FallbackAnswerGenerator:
    """Generate simple answers from retrieved chunks when LLM unavailable."""
    
    def get_fallback_answer(self, question: str, course=None, chunks: list[str] = None) -> str:
        """Get fallback answer when LLM is down."""
        return "LLM service is currently unavailable. Please ensure Ollama is running."

    @staticmethod
    def generate_from_chunks(question: str, chunks: list[str], max_length: int = 300) -> str:
        """Create answer by extracting most relevant sentences from chunks."""
        if not chunks:
            return "I couldn't find that information in the course materials."
        
        # Find sentences most relevant to question
        question_words = set(question.lower().split())
        scored_sentences = []
        
        for chunk in chunks[:3]:  # Use top 3 chunks only
            for line in chunk.split('\n'):
                line = line.strip()
                if len(line) < 20 or len(line) > 500:
                    continue
                
                # Score by word overlap
                line_words = set(line.lower().split())
                overlap = len(question_words & line_words)
                if overlap > 0:
                    scored_sentences.append((overlap, line))
        
        if not scored_sentences:
            # Last resort: just take first chunk
            return chunks[0][:max_length] + "..."
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[0], reverse=True)
        result_lines = [s[1] for s in scored_sentences[:2]]
        
        answer = " ".join(result_lines)
        if len(answer) > max_length:
            answer = answer[:max_length] + "..."
        
        return answer
    
    @staticmethod
    def generate_mcq_grading_fallback(questions: list[dict], answers: dict, 
                                      answer_key: dict) -> dict:
        """Grade MCQ submission when LLM unavailable (deterministic)."""
        score_breakdown = []
        total = 0
        
        def normalize(val):
            import re
            return re.sub(r"\s+", " ", str(val or "").strip().lower().rstrip(".:-"))
        
        for index, question in enumerate(questions, start=1):
            question_num = int(question.get("question_number", index))
            max_score = int(question.get("marks", 1))
            
            # Get correct answer
            correct_answer = answer_key.get(str(question_num), {}).get("correct_option", "")
            student_answer = str(answers.get(question_num, answers.get(str(question_num), ""))).strip()
            
            is_correct = bool(correct_answer) and normalize(student_answer) == normalize(correct_answer)
            score = max_score if is_correct else 0
            total += score
            
            score_breakdown.append({
                "question_number": question_num,
                "score": score,
                "max_score": max_score,
                "is_correct": is_correct,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "feedback": "Correct!" if is_correct else f"Incorrect. Expected: {correct_answer}",
            })
        
        return {
            "total_score": total,
            "score_breakdown": score_breakdown,
            "overall_feedback": f"Your score: {total} / {sum(q.get('marks', 1) for q in questions)}",
            "grading_mode": "fallback-deterministic",
            "ai_feedback": {"note": "LLM unavailable - deterministic grading used"},
        }

    @staticmethod
    def is_available(error: Optional[Exception] = None) -> bool:
        """Check if LLM service is available."""
        # In real implementation, this would ping Ollama
        if error:
            logger.warning(f"LLM service unavailable: {error}")
            return False
        return True


def get_fallback_answer(question: str, chunks: list[str]) -> str:
    """Get fallback answer when LLM is down."""
    generator = FallbackAnswerGenerator()
    answer = generator.generate_from_chunks(question, chunks)
    
    # Add disclaimer
    return f"{answer}\n\n*Note: LLM service is temporarily unavailable. This answer is based on direct extraction from course materials.*"


def grade_with_fallback(assignment, answers: dict) -> dict:
    """Grade submission with fallback when LLM unavailable."""
    from apps.assignments.models import AssignmentType
    
    if assignment.type != AssignmentType.MCQ:
        # Can't auto-grade non-MCQ without LLM
        return {
            "total_score": 0,
            "score_breakdown": [],
            "overall_feedback": "Grading temporarily unavailable. Submission queued for when service returns.",
            "grading_mode": "queued",
            "ai_feedback": {"status": "pending", "reason": "LLM unavailable"},
        }
    
    # Use deterministic MCQ grading
    generator = FallbackAnswerGenerator()
    return generator.generate_mcq_grading_fallback(
        assignment.questions, 
        answers, 
        assignment.answer_key
    )
