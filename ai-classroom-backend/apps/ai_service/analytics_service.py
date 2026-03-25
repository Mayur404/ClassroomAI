"""
Analytics and insights service.
Tracks system usage, identifies struggle areas, and provides recommendations.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from apps.chat.models import ChatMessage
from apps.submissions.models import Submission
from apps.courses.models import Course
from apps.assignments.models import Assignment

logger = logging.getLogger(__name__)


class CourseAnalyticsService:
    """Analyze course engagement and performance."""
    
    @staticmethod
    def get_frequently_asked_topics(course_id: int, days: int = 30) -> list[dict]:
        """Find most asked about topics."""
        cutoff = timezone.now() - timedelta(days=days)
        messages = ChatMessage.objects.filter(
            course_id=course_id,
            timestamp__gte=cutoff,
        ).values('message')
        
        # Group by keywords
        topic_counts = {}
        keywords = ['algorithm', 'data', 'function', 'class', 'definition', 'example', 
                   'implement', 'question', 'problem', 'what', 'how', 'why']
        
        for msg in messages:
            text = msg['message'].lower()
            for keyword in keywords:
                if keyword in text:
                    topic_counts[keyword] = topic_counts.get(keyword, 0) + 1
        
        return sorted(
            [{'topic': k, 'count': v} for k, v in topic_counts.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:10]
    
    @staticmethod
    def get_helpful_answers_stats(course_id: int) -> dict:
        """Analyze which answers were helpful."""
        messages = ChatMessage.objects.filter(
            course_id=course_id,
            feedback_score__isnull=False,
        )
        
        helpful = messages.filter(feedback_score=1).count()
        unhelpful = messages.filter(feedback_score=-1).count()
        total = helpful + unhelpful
        
        if total == 0:
            return {
                "helpful_percentage": 0,
                "helpful_count": 0,
                "unhelpful_count": 0,
                "sample_size": 0,
            }
        
        return {
            "helpful_percentage": round((helpful / total) * 100, 1),
            "helpful_count": helpful,
            "unhelpful_count": unhelpful,
            "sample_size": total,
        }
    
    @staticmethod
    def get_performance_by_topic(course_id: int) -> list[dict]:
        """Get student performance broken down by topic."""
        assignments = Assignment.objects.filter(course_id=course_id)
        results = []
        
        for assignment in assignments:
            submissions = Submission.objects.filter(assignment=assignment)
            if not submissions.exists():
                continue
            
            avg_score = submissions.aggregate(avg=Avg('ai_grade'))['avg'] or 0
            submission_count = submissions.count()
            
            results.append({
                "topic": assignment.title,
                "average_score": round(avg_score, 2),
                "submission_count": submission_count,
                "max_marks": assignment.total_marks,
                "performance": "Good" if avg_score >= 70 else "Needs Improvement" if avg_score >= 50 else "Critical",
            })
        
        return sorted(results, key=lambda x: x['average_score'])
    
    @staticmethod
    def get_student_struggle_areas(course_id: int, student_id: int) -> list[str]:
        """Identify topics where a student struggled."""
        submissions = Submission.objects.filter(
            assignment__course_id=course_id,
            student_id=student_id,
        )
        
        struggle_topics = []
        for submission in submissions:
            if submission.ai_grade < 50:  # Below 50% is struggle
                struggle_topics.append(submission.assignment.title)
        
        return struggle_topics


class StudentRecommendationService:
    """Provide personalized learning recommendations."""
    
    @staticmethod
    def get_recommended_review_topics(course_id: int, student_id: int) -> list[str]:
        """Topics the student should review."""
        analytics = CourseAnalyticsService()
        struggle_areas = analytics.get_student_struggle_areas(course_id, student_id)
        return struggle_areas[:5]  # Top 5 struggle areas
    
    @staticmethod
    def get_learning_path_progress(course_id: int, student_id: int) -> dict:
        """Get student's progress through course."""
        assignments = Assignment.objects.filter(course_id=course_id)
        total = assignments.count()
        
        completed = Submission.objects.filter(
            assignment__course_id=course_id,
            student_id=student_id,
            status='GRADED'
        ).values('assignment').distinct().count()
        
        return {
            "total_assignments": total,
            "completed": completed,
            "remaining": total - completed,
            "progress_percentage": round((completed / total * 100), 1) if total > 0 else 0,
        }
    
    @staticmethod
    def get_personalized_assignments(course_id: int, student_id: int) -> list[dict]:
        """Suggest next assignments based on progress."""
        progress = StudentRecommendationService.get_learning_path_progress(course_id, student_id)
        
        # Get incomplete assignments
        completed_ids = Submission.objects.filter(
            assignment__course_id=course_id,
            student_id=student_id,
        ).values_list('assignment_id', flat=True)
        
        pending = Assignment.objects.filter(
            course_id=course_id,
            status='PUBLISHED'
        ).exclude(id__in=completed_ids).values('id', 'title', 'due_date', 'type')
        
        return list(pending[:5])


def get_course_insights(course_id: int) -> dict:
    """Get comprehensive course insights."""
    analytics = CourseAnalyticsService()
    
    return {
        "frequently_asked_topics": analytics.get_frequently_asked_topics(course_id),
        "helpful_answers_stats": analytics.get_helpful_answers_stats(course_id),
        "performance_by_topic": analytics.get_performance_by_topic(course_id),
    }


def get_student_insights(course_id: int, student_id: int) -> dict:
    """Get insights for a specific student."""
    recommendations = StudentRecommendationService()
    
    return {
        "progress": recommendations.get_learning_path_progress(course_id, student_id),
        "review_topics": recommendations.get_recommended_review_topics(course_id, student_id),
        "next_assignments": recommendations.get_personalized_assignments(course_id, student_id),
    }
