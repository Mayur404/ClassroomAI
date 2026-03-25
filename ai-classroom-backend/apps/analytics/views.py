from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import Course
from apps.submissions.models import Submission


class CourseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        assignments = course.assignments.all()
        submissions = Submission.objects.filter(assignment__course=course)
        average_score = assignments.aggregate(avg=Avg("submissions__ai_grade"))["avg"] or 0
        latest_submission = submissions.order_by("-submitted_at").first()
        assignment_type_breakdown = list(
            assignments.values("type").annotate(count=Count("id")).order_by("type")
        )
        return Response(
            {
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
            }
        )
