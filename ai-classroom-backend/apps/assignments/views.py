from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import generate_assignment_for_course
from apps.courses.models import Course, ScheduleStatus

from .models import Assignment, AssignmentStatus
from .serializers import AssignmentGenerateSerializer, AssignmentSerializer


class AssignmentListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        return Assignment.objects.filter(course_id=self.kwargs["course_id"])

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AssignmentDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = AssignmentSerializer
    queryset = Assignment.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AssignmentGenerateView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id)
        serializer = AssignmentGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Use extracted topics as covered topics for the demo
        covered_topics = course.extracted_topics or ["General course content"]

        payload = generate_assignment_for_course(
            course=course,
            assignment_type=serializer.validated_data["type"],
            title=serializer.validated_data["title"],
            covered_topics=covered_topics,
        )

        assignment = Assignment.objects.create(
            course=course,
            title=payload["title"],
            description=payload.get("description", ""),
            type=payload.get("type", serializer.validated_data["type"]),
            total_marks=payload.get("total_marks", 100),
            questions=payload.get("questions", []),
            rubric=payload.get("rubric", []),
            answer_key=payload.get("answer_key", {}),
            due_date=serializer.validated_data["due_date"],
            covered_until_class=0,
            status=AssignmentStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        return Response(AssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AssignmentPublishView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, assignment_id):
        assignment = Assignment.objects.get(id=assignment_id)
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.published_at = timezone.now()
        assignment.save(update_fields=["status", "published_at"])
        return Response(AssignmentSerializer(assignment, context={"request": request}).data)
