from django.db.models import Avg
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import Course


class CourseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        course = Course.objects.get(id=course_id)
        average_score = course.assignments.aggregate(avg=Avg("submissions__ai_grade"))["avg"] or 0
        return Response(
            {
                "course_id": course.id,
                "course_name": course.name,
                "assignment_count": course.assignments.count(),
                "submission_count": course.assignments.values("submissions__id").count(),
                "average_score": round(average_score, 2),
                "enrollment_count": course.enrollments.count(),
            }
        )
