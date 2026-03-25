from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import generate_assignment_for_course
from apps.courses.models import Course, ScheduleStatus
from apps.submissions.models import Submission

from .models import Assignment, AssignmentStatus
from .serializers import AssignmentGenerateSerializer, AssignmentSerializer


def _assignment_queryset_for_user(user):
    return (
        Assignment.objects.select_related("course")
        .prefetch_related(
            Prefetch(
                "submissions",
                queryset=Submission.objects.filter(student=user).order_by("-submitted_at"),
                to_attr="request_user_submissions",
            )
        )
    )


class AssignmentListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        course = get_object_or_404(Course, id=self.kwargs["course_id"], teacher=self.request.user)
        return _assignment_queryset_for_user(self.request.user).filter(course=course)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AssignmentDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        return _assignment_queryset_for_user(self.request.user).filter(course__teacher=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AssignmentGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        serializer = AssignmentGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        covered_topics = []
        covered_outline = []
        seen = set()
        schedule_items = list(course.schedule_items.order_by("class_number", "order_index"))
        completed_items = [item for item in schedule_items if item.status == ScheduleStatus.COMPLETED]
        planned_scope = completed_items or schedule_items[: min(3, len(schedule_items))]

        for item in planned_scope:
            normalized = str(item.topic).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            covered_topics.append(normalized)
            covered_outline.append(
                {
                    "topic": normalized,
                    "subtopics": item.subtopics or [],
                    "learning_objectives": item.learning_objectives or [],
                }
            )

        if not covered_topics:
            topic_sources = list(course.extracted_topics or [])
            if not topic_sources:
                for material in course.materials.all():
                    topic_sources.extend(material.extracted_topics or [])

            for topic in topic_sources:
                normalized = str(topic).strip()
                if not normalized:
                    continue
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                covered_topics.append(normalized)
                covered_outline.append(
                    {
                        "topic": normalized,
                        "subtopics": [],
                        "learning_objectives": [],
                    }
                )

        if not covered_topics:
            return Response(
                {"detail": "Upload and analyze course materials before generating assignments."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = generate_assignment_for_course(
            course=course,
            assignment_type=serializer.validated_data["type"],
            title=serializer.validated_data["title"],
            covered_topics=covered_topics,
            covered_outline=covered_outline,
        )
        completed_classes = len(completed_items)
        covered_until_class = completed_classes or len(planned_scope) or min(course.schedule_items.count() or len(covered_topics), len(covered_topics))

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
            covered_until_class=covered_until_class,
            status=AssignmentStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        return Response(AssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AssignmentPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(Assignment, id=assignment_id, course__teacher=request.user)
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.published_at = timezone.now()
        assignment.save(update_fields=["status", "published_at"])
        return Response(AssignmentSerializer(assignment, context={"request": request}).data)
