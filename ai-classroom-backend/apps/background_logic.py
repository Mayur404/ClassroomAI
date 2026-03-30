"""
Core logic for heavy tasks like PDF extraction and indexing.
Now runs synchronously without Celery/Redis.
"""
import logging
from .courses.models import CourseMaterial, ParseStatus

logger = logging.getLogger(__name__)

# ============================================================================
# TASK LOGIC
# ============================================================================

def extract_pdf_logic(material_id: int, file_path: str):
    """
    Extract text from PDF synchronously.
    """
    try:
        from apps.ai_service.services import extract_pdf_content
        
        material = CourseMaterial.objects.get(id=material_id)
        
        logger.info(f"Extracting PDF for material {material_id}")
        material.parse_status = ParseStatus.PENDING
        material.save(update_fields=['parse_status'])
        
        # Run extraction pipeline
        result = extract_pdf_content(file_path)
        
        if result['text']:
            material.content_text = result['text']
            material.parse_status = ParseStatus.SUCCESS
            material.save(update_fields=['content_text', 'parse_status'])
            
            # Run indexing synchronously
            index_material_logic(material_id)
            
            logger.info(f"Material {material_id} extracted successfully")
            return {"success": True, "text": result['text']}
        else:
            material.parse_status = ParseStatus.FAILED
            material.save(update_fields=['parse_status'])
            logger.error(f"Extraction failed for {material_id}: No text found")
            return {"success": False, "error": "No text found"}
    
    except Exception as exc:
        logger.error(f"Error extracting PDF {material_id}: {str(exc)}")
        if 'material' in locals():
            material.parse_status = ParseStatus.FAILED
            material.save(update_fields=['parse_status'])
        return {"success": False, "error": str(exc)}


def index_material_logic(material_id: int):
    """
    Index material in vector database.
    """
    try:
        from apps.ai_service.rag_service import index_course_materials
        from apps.ai_service.enhanced_rag import index_material_with_structure
        
        material = CourseMaterial.objects.get(id=material_id)
        course_id = material.course_id
        
        logger.info(f"Indexing material {material_id} for course {course_id}")
        
        # Call RAG indexing
        index_result = index_course_materials(course_id, material.id, material.content_text)
        
        # Also build document structure for enhanced heading-based queries
        structure_result = index_material_with_structure(course_id, material.id, material.content_text)
        
        material.extracted_topics = index_result.get("topics", [])
        material.parse_status = ParseStatus.SUCCESS if index_result["status"] == "SUCCESS" else ParseStatus.FAILED
        material.save(update_fields=['extracted_topics', 'parse_status'])
        
        logger.info(f"Material {material_id} indexed successfully")
        return {"success": True, "index_result": index_result, "structure_result": structure_result}
    
    except Exception as exc:
        logger.error(f"Error indexing material {material_id}: {str(exc)}")
        if 'material' in locals():
            material.parse_status = ParseStatus.FAILED
            material.save(update_fields=['parse_status'])
        return {"success": False, "error": str(exc)}


def generate_assignment_logic(course_id: int, assignment_type: str, num_questions: int):
    """
    Generate assignment synchronously.
    """
    try:
        from apps.courses.models import Course
        from apps.ai_service.services import generate_assignment_for_course
        from apps.assignments.models import Assignment, AssignmentStatus
        from django.utils import timezone
        from datetime import timedelta
        import uuid
        
        course = Course.objects.get(id=course_id)
        
        logger.info(f"Generating {assignment_type} assignment for course {course_id}")
        
        # This is a simplified version of the logic in assignments/views.py
        # In a real app, you'd want to share this code.
        covered_topics = list(course.extracted_topics[:num_questions])
        
        payload = generate_assignment_for_course(
            course=course,
            assignment_type=assignment_type,
            title=f"Auto-generated {assignment_type}",
            covered_topics=covered_topics,
        )
        
        assignment = Assignment.objects.create(
            course=course,
            title=payload["title"],
            description=payload.get("description", ""),
            type=assignment_type,
            total_marks=payload.get("total_marks", 100),
            questions=payload.get("questions", []),
            rubric=payload.get("rubric", []),
            answer_key=payload.get("answer_key", {}),
            due_date=timezone.now() + timedelta(days=7),
            status=AssignmentStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        
        logger.info(f"Assignment {assignment.id} generated successfully")
        
        return {
            "assignment_id": assignment.id,
            "status": "completed"
        }
    
    except Exception as exc:
        logger.error(f"Error generating assignment: {str(exc)}")
        return {"success": False, "error": str(exc)}


def grade_submission_logic(submission_id: int):
    """
    Grade student submission synchronously.
    """
    try:
        from apps.submissions.models import Submission, SubmissionStatus
        from apps.ai_service.services import grade_submission
        from django.utils import timezone
        
        submission = Submission.objects.get(id=submission_id)
        
        logger.info(f"Grading submission {submission_id}")
        
        result = grade_submission(assignment=submission.assignment, answers=submission.answers)
        
        submission.ai_grade = result["total_score"]
        submission.ai_feedback = result.get("ai_feedback", {"overall_feedback": result["overall_feedback"]})
        submission.score_breakdown = result["score_breakdown"]
        submission.status = SubmissionStatus.GRADED
        submission.graded_at = timezone.now()
        submission.save()
        
        logger.info(f"Submission {submission_id} graded: {submission.ai_grade}")
        
        return result
    
    except Exception as exc:
        logger.error(f"Error grading submission {submission_id}: {str(exc)}")
        return {"success": False, "error": str(exc)}


def bulk_process_materials_logic(course_id: int, material_ids: list):
    """
    Process multiple materials in batch.
    """
    logger.info(f"Bulk processing {len(material_ids)} materials for course {course_id}")
    
    results = []
    for material_id in material_ids:
        try:
            material = CourseMaterial.objects.get(id=material_id, course_id=course_id)
            extract_pdf_logic(material_id, material.file.path)
            results.append({"material_id": material_id, "processed": True})
        except Exception as e:
            logger.error(f"Failed to process material {material_id}: {str(e)}")
            results.append({"material_id": material_id, "error": str(e)})
    
    return results
