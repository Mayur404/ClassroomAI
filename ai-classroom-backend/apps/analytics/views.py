from django.db.models import Avg, Count, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.courses.models import Course
from apps.submissions.models import Submission
from apps.chat.models import ChatMessage
from apps.assignments.models import Assignment
from apps.ai_service.analytics_service import (
    CourseAnalyticsService,
    StudentRecommendationService,
)


class CourseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        """
        Get comprehensive course analytics including RAG metrics.
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        
        # Basic assignment analytics
        assignments = course.assignments.all()
        submissions = Submission.objects.filter(assignment__course=course)
        average_score = assignments.aggregate(avg=Avg(Coalesce("submissions__teacher_grade", "submissions__ai_grade")))["avg"] or 0
        latest_submission = submissions.order_by("-submitted_at").first()
        assignment_type_breakdown = list(
            assignments.values("type").annotate(count=Count("id")).order_by("type")
        )
        
        # Enhanced: Chat and RAG analytics
        all_messages = ChatMessage.objects.filter(course=course)
        total_with_feedback = all_messages.filter(feedback_score__isnull=False).count()
        helpful_count = all_messages.filter(feedback_score=1).count()
        unhelpful_count = all_messages.filter(feedback_score=-1).count()
        
        # Frequently asked topics (using analytics service)
        try:
            frequently_asked = CourseAnalyticsService.get_frequently_asked_topics(course_id=course.id)[:5]
            student_struggles = []  # struggle areas requires a student_id, skip for course-level view
        except Exception:
            frequently_asked = []
            student_struggles = []
        
        # Engagement metrics
        last_week = timezone.now() - timedelta(days=7)
        messages_last_week = all_messages.filter(timestamp__gte=last_week).count()
        unique_students = all_messages.values('student').distinct().count()
        
        return Response({
            # Original fields
            "course_id": course.id,
            "course_name": course.name,
            "assignment_count": assignments.count(),
            "submission_count": submissions.count(),
            "average_score": round(average_score, 2),
            "enrollment_count": course.enrollments.count(),
            "completed_class_count": course.schedule_items.filter(status="COMPLETED").count(),
            "schedule_item_count": course.schedule_items.count(),
            "assignment_type_breakdown": assignment_type_breakdown,
            "latest_submission_at": latest_submission.submitted_at if latest_submission else None,
            # New RAG analytics
            "chat_analytics": {
                "total_messages": all_messages.count(),
                "messages_with_feedback": total_with_feedback,
                "helpful_count": helpful_count,
                "unhelpful_count": unhelpful_count,
                "helpful_percentage": round(
                    (helpful_count / max(total_with_feedback, 1) * 100) if total_with_feedback else 0,
                    1
                ),
                "feedback_rate": round(
                    (total_with_feedback / max(all_messages.count(), 1) * 100) if all_messages.count() else 0,
                    1
                ),
                "unique_students_asked": unique_students,
                "messages_last_week": messages_last_week,
            },
            "frequently_asked_topics": frequently_asked,
            "student_struggle_areas": student_struggles,
        })


class StudentAnalyticsView(APIView):
    """Get personalized analytics for a student."""
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        """
        Get personalized analytics for a student.
        """
        # Verify access (student can only see their own, teachers see their students)
        if student_id != request.user.id:
            # Check if user is a teacher of a course this student is in
            from django.contrib.auth.models import User
            student = get_object_or_404(User, id=student_id)
            has_access = False
            for course in Course.objects.filter(teacher=request.user):
                if course.enrollments.filter(student=student).exists():
                    has_access = True
                    break
            
            if not has_access:
                return Response(
                    {"detail": "You don't have permission to view this student's analytics."},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            from django.contrib.auth.models import User
            student = get_object_or_404(User, id=student_id)
        
        # Get performance summary
        all_messages = ChatMessage.objects.filter(student=student)
        helpful_messages = all_messages.filter(feedback_score=1).count()
        total_messages = all_messages.count()
        
        # Get learning patterns
        last_week = timezone.now() - timedelta(days=7)
        recent_messages = all_messages.filter(timestamp__gte=last_week)
        
        performance_summary = {
            "total_questions_asked": total_messages,
            "helpful_answers_received": helpful_messages,
            "helpful_percentage": round(
                (helpful_messages / max(total_messages, 1) * 100) if total_messages else 0,
                1
            ),
            "courses_engaged": all_messages.values('course').distinct().count(),
            "messages_last_week": recent_messages.count(),
            "average_response_time": self._get_avg_response_time(student),
        }
        
        # Get personalized recommendations
        try:
            # Find courses this student is associated with
            from apps.courses.models import Course
            student_courses = Course.objects.filter(
                chat_messages__student=student
            ).distinct()[:1]
            if student_courses:
                course_id = student_courses[0].id
                recommended_topics = StudentRecommendationService.get_recommended_review_topics(course_id, student.id)[:5]
                personalized_assignments = StudentRecommendationService.get_personalized_assignments(course_id, student.id)[:5]
            else:
                recommended_topics = []
                personalized_assignments = []
        except Exception:
            recommended_topics = []
            personalized_assignments = []
        
        return Response({
            "student_id": student.id,
            "student_name": student.get_full_name() or student.username,
            "performance_summary": performance_summary,
            "recommended_review_topics": recommended_topics,
            "personalized_assignments": personalized_assignments,
            "learning_pace": self._get_learning_pace(student),
        })
    
    def _get_avg_response_time(self, student):
        """Get average time between asking and getting answer."""
        messages = ChatMessage.objects.filter(student=student, role='STUDENT').order_by('timestamp')
        if messages.count() < 2:
            return 0
        
        # Estimate from message frequency
        first = messages.first()
        last = messages.last()
        
        if (last.timestamp - first.timestamp).total_seconds() > 0:
            avg_seconds = (last.timestamp - first.timestamp).total_seconds() / messages.count()
            return round(avg_seconds / 60, 1)  # Convert to minutes
        
        return 0
    
    def _get_learning_pace(self, student):
        """Determine student's learning pace."""
        last_week = timezone.now() - timedelta(days=7)
        recent = ChatMessage.objects.filter(
            student=student,
            timestamp__gte=last_week
        ).count()
        
        if recent > 30:
            return "Very Active"
        elif recent > 10:
            return "Active"
        elif recent > 2:
            return "Moderate"
        elif recent > 0:
            return "Light"
        else:
            return "Inactive"


class TopicAnalyticsView(APIView):
    """Get analytics for specific topics across courses."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get topic analytics across courses taught by the user.
        """
        search_keyword = request.query_params.get('search', '')
        limit = int(request.query_params.get('limit', 20))
        
        # Find messages from user's courses
        messages = ChatMessage.objects.filter(
            course__teacher=request.user
        )
        
        if search_keyword:
            messages = messages.filter(
                Q(message__icontains=search_keyword) |
                Q(ai_response__icontains=search_keyword)
            )
        
        # Analyze topics
        topics_data = {}
        
        for msg in messages:
            # Extract keywords (simplified - in production use NLP)
            words = msg.message.lower().split()
            for word in words:
                if len(word) > 4:  # Filter short words
                    word = word.strip('.,!?;:\'"-')
                    if len(word) > 4:
                        if word not in topics_data:
                            topics_data[word] = {
                                "total": 0,
                                "helpful": 0,
                                "unhelpful": 0,
                            }
                        
                        topics_data[word]["total"] += 1
                        if msg.feedback_score == 1:
                            topics_data[word]["helpful"] += 1
                        elif msg.feedback_score == -1:
                            topics_data[word]["unhelpful"] += 1
        
        # Format response
        topics = []
        for topic, data in sorted(
            topics_data.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )[:limit]:
            helpful_pct = (data["helpful"] / max(data["total"], 1) * 100) if data["total"] else 0
            
            topics.append({
                "topic": topic,
                "total_questions": data["total"],
                "helpful_percentage": round(helpful_pct, 1),
                "trending": data["total"] > 5,
            })
        
        return Response({"topics": topics})


class ErrorLogView(APIView):
    """
    Endpoint for frontend error reporting.
    Accepts error details from the ErrorBoundary and logs them.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        error_data = request.data
        correlation_id = error_data.get('correlationId', 'unknown')
        message = error_data.get('message', 'No message')
        stack = error_data.get('stack', 'No stack trace')
        url = error_data.get('url', 'Unknown URL')
        
        logger.error(
            f"FRONTEND_ERROR [{correlation_id}] on {url}: {message}\n"
            f"Stack: {stack[:1000]}..."
        )
        
        # In production, this might also send to Sentry or a database
        # For now, we just log it and return success
        return Response({"status": "received", "id": correlation_id}, status=status.HTTP_201_CREATED)
