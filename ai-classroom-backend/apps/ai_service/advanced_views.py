"""
API views for advanced features:
- Adaptive difficulty recommendations
- Conversation summaries and export  
- Feedback analysis insights
"""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.http import FileResponse
import io
from django.contrib.auth.models import User

from apps.courses.models import Course
from apps.ai_service.adaptive_difficulty import AdaptiveDifficultyService
from apps.ai_service.conversation_service import ConversationSummaryService
from apps.ai_service.feedback_analysis import FeedbackAnalysisService


class AdaptiveDifficultyView(APIView):
    """Get adaptive difficulty recommendations for a student."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, student_id):
        """
        Get difficulty recommendations and learning path for a student.
        
        Returns:
        {
            "student_id": 123,
            "course_id": 1,
            "performance": {...},
            "recommended_difficulty": "INTERMEDIATE",
            "next_assignment_recommendations": [...],
            "learning_path": [...],
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is in course
        if student not in course.students.all():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        service = AdaptiveDifficultyService()
        
        performance = service.get_student_performance(student, course)
        recommendation = service.recommend_next_difficulty(student, course)
        assignments = service.get_assignment_recommendations(student, course, limit=5)
        learning_path = service.estimate_learning_path(student, course)
        
        return Response({
            "student_id": student.id,
            "student_name": student.get_full_name() or student.username,
            "course_id": course.id,
            "course_name": course.name,
            "performance": performance,
            "recommended_difficulty": recommendation["recommended_difficulty"],
            "recommendation_reason": recommendation["reason"],
            "recommendation_confidence": recommendation["confidence"],
            "result": "success",
            "next_assignment_recommendations": assignments,
            "suggested_learning_path": learning_path,
        })


class ConversationSummaryView(APIView):
    """Get summaries and insights about conversations."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, student_id):
        """
        Get summary and insights for a student's conversation in a course.
        
        Query params:
        - max_messages: Limit to last N messages (optional)
        
        Returns:
        {
            "summary": {...},
            "insights": {...},
            "export_formats": [formats available],
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is in course
        if student not in course.students.all():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        max_messages = request.query_params.get('max_messages', None)
        if max_messages:
            max_messages = int(max_messages)
        
        service = ConversationSummaryService()
        
        summary = service.summarize_conversation(student, course, max_messages=max_messages)
        insights = service.get_conversation_insights(student, course)
        
        return Response({
            "student_id": student.id,
            "student_name": student.get_full_name() or student.username,
            "course_id": course.id,
            "course_name": course.name,
            "summary": summary,
            "insights": insights,
            "export_formats": ['json', 'markdown', 'csv', 'text'],
            "export_url": f"/api/conversations/{student_id}/courses/{course_id}/export/",
        })


class ConversationExportView(APIView):
    """Export conversations in various formats."""
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id, course_id):
        """
        Export a conversation.
        
        Query params:
        - format: 'json', 'markdown', 'csv', or 'text' (default: json)
        - max_messages: Limit to last N messages (optional)
        
        Returns:
            File download or JSON
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is in course
        if student not in course.students.all():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        export_format = request.query_params.get('format', 'json')
        max_messages = request.query_params.get('max_messages', None)
        
        if max_messages:
            max_messages = int(max_messages)
        
        if export_format not in ['json', 'markdown', 'csv', 'text']:
            return Response(
                {"detail": f"Unknown format: {export_format}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ConversationSummaryService()
        content = service.export_conversation(
            student, course, format=export_format, max_messages=max_messages
        )
        
        # Determine file extension and content type
        extensions = {
            'json': ('json', 'application/json'),
            'markdown': ('md', 'text/markdown'),
            'csv': ('csv', 'text/csv'),
            'text': ('txt', 'text/plain'),
        }
        
        ext, content_type = extensions[export_format]
        filename = f"conversation_{student.username}_{course.id}.{ext}"
        
        # Create file-like object
        file_obj = io.BytesIO(content.encode('utf-8'))
        file_obj.seek(0)
        
        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=content_type
        )


class FeedbackAnalysisView(APIView):
    """Get feedback analysis and improvement recommendations."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        """
        Get comprehensive feedback analysis for a course.
        
        Returns:
        {
            "quality_metrics": {...},
            "problem_areas": [...],
            "patterns": {...},
            "recommendations": [...],
            "topic_difficulty": {...},
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        
        service = FeedbackAnalysisService()
        
        metrics = service.get_feedback_quality_metrics(course)
        problems = service.identify_problem_areas(course, limit=10)
        patterns = service.get_feedback_patterns(course)
        recommendations = service.get_improvement_recommendations(course)
        difficulties = service.calculate_topic_difficulty(course)
        
        return Response({
            "course_id": course.id,
            "course_name": course.name,
            "quality_metrics": metrics,
            "problem_areas": problems,
            "feedback_patterns": patterns,
            "improvement_recommendations": recommendations,
            "topic_difficulty": difficulties,
            "summary": {
                "overall_health": "good" if metrics["helpful_rate"] >= 0.7 else "needs_improvement",
                "areas_to_focus": [p["topic"] for p in problems[:3]],
                "priority_action": recommendations[0]["recommendation"] if recommendations else "No improvements needed",
            }
        })


class DashboardMetricsView(APIView):
    """Get all metrics for instructor dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get all dashboard metrics for user's courses.
        
        Returns:
        {
            "courses": [
                {
                    "course_id": 1,
                    "course_name": "Python 101",
                    "metrics": {...},
                }
            ],
            "aggregate_metrics": {...},
        }
        """
        courses = Course.objects.filter(teacher=request.user)
        
        feedback_service = FeedbackAnalysisService()
        
        course_data = []
        all_metrics = {
            "total_students": 0,
            "total_questions": 0,
            "average_helpful_rate": [],
        }
        
        for course in courses:
            metrics = feedback_service.get_feedback_quality_metrics(course)
            problems = feedback_service.identify_problem_areas(course, limit=3)
            
            all_metrics["total_students"] += course.students.count()
            all_metrics["total_questions"] += sum(1 for _ in metrics)
            all_metrics["average_helpful_rate"].append(metrics["helpful_rate"])
            
            course_data.append({
                "course_id": course.id,
                "course_name": course.name,
                "student_count": course.students.count(),
                "helpful_rate": metrics["helpful_rate"],
                "feedback_rate": metrics["feedback_rate"],
                "trend": metrics["trend"],
                "top_problem_areas": [p["topic"] for p in problems[:3]],
            })
        
        # Calculate aggregate
        if all_metrics["average_helpful_rate"]:
            avg_rate = sum(all_metrics["average_helpful_rate"]) / len(all_metrics["average_helpful_rate"])
        else:
            avg_rate = 0
        
        return Response({
            "courses": course_data,
            "aggregate": {
                "total_courses": courses.count(),
                "total_students": all_metrics["total_students"],
                "average_helpful_rate": round(avg_rate, 2),
            }
        })
