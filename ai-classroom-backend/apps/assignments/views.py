from django.db.models import Avg, Count, Prefetch
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import generate_assignment_for_course
from apps.courses.models import Course, ScheduleStatus
from apps.submissions.models import Submission

from .models import Assignment, AssignmentStatus
from .serializers import AssignmentGenerateSerializer, AssignmentSerializer


def _assignment_queryset_for_user(user):
    queryset = (
        Assignment.objects.select_related("course")
        .annotate(
            submission_count_value=Count("submissions", distinct=True),
            enrollment_count_value=Count("course__enrollments", distinct=True),
            average_score_value=Avg(Coalesce("submissions__teacher_grade", "submissions__ai_grade")),
        )
        .prefetch_related(
            Prefetch(
                "submissions",
                queryset=Submission.objects.filter(student=user).select_related("student", "assignment").order_by("-submitted_at"),
                to_attr="request_user_submissions",
            )
        )
    )
    if getattr(user, "role", None) == "TEACHER":
        queryset = queryset.prefetch_related(
            Prefetch(
                "submissions",
                queryset=Submission.objects.select_related("student", "assignment").order_by("-submitted_at"),
                to_attr="teacher_visible_submissions",
            )
        )
    return queryset


class AssignmentListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        if self.request.user.role == "TEACHER":
            course = get_object_or_404(Course, id=self.kwargs["course_id"], teacher=self.request.user)
            return _assignment_queryset_for_user(self.request.user).filter(course=course)
        else:
            course = get_object_or_404(Course, id=self.kwargs["course_id"], enrollments__student=self.request.user)
            return _assignment_queryset_for_user(self.request.user).filter(
                course=course,
                status=AssignmentStatus.PUBLISHED,
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        if self.request.user.role == "TEACHER":
            return _assignment_queryset_for_user(self.request.user).filter(course__teacher=self.request.user)
        return _assignment_queryset_for_user(self.request.user).filter(
            course__enrollments__student=self.request.user,
            status=AssignmentStatus.PUBLISHED,
        ).distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def destroy(self, request, *args, **kwargs):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can delete assignments.")
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can edit assignments.")
        return super().update(request, *args, **kwargs)


class AssignmentGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can generate assignments.")
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
            # Fallback when topic extraction metadata is sparse: infer from raw material text.
            for material in course.materials.all()[:8]:
                raw = (material.content_text or "").strip()
                if not raw:
                    continue
                candidate = raw.split(".")[0].strip()[:120]
                if not candidate:
                    continue
                covered_topics.append(candidate)
                covered_outline.append(
                    {
                        "topic": candidate,
                        "subtopics": [],
                        "learning_objectives": [],
                    }
                )
                if len(covered_topics) >= 4:
                    break

        if not covered_topics:
            fallback_topic = f"Core concepts in {course.name}"
            covered_topics = [fallback_topic]
            covered_outline = [
                {
                    "topic": fallback_topic,
                    "subtopics": [],
                    "learning_objectives": ["Demonstrate understanding of core concepts."],
                }
            ]

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
            status=AssignmentStatus.DRAFT,
            published_at=None,
        )
        return Response(AssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AssignmentPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, assignment_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can publish assignments.")
        assignment = get_object_or_404(Assignment, id=assignment_id, course__teacher=request.user)
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.published_at = timezone.now()
        assignment.save(update_fields=["status", "published_at"])
        return Response(AssignmentSerializer(assignment, context={"request": request}).data)


class AssignmentManualCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can upload assignments.")

        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        title = str(request.data.get("title", "")).strip()
        assignment_type = str(request.data.get("type", "ESSAY")).strip().upper()
        description = str(request.data.get("description", "")).strip()
        questions = request.data.get("questions", [])
        rubric = request.data.get("rubric", [])
        total_marks = int(request.data.get("total_marks", 100) or 100)
        due_date = request.data.get("due_date")

        if not title:
            return Response({"detail": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        if assignment_type not in {"MCQ", "ESSAY", "CODING"}:
            return Response({"detail": "type must be MCQ, ESSAY or CODING"}, status=status.HTTP_400_BAD_REQUEST)
        if not due_date:
            return Response({"detail": "due_date is required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AssignmentGenerateSerializer(
            data={
                "title": title,
                "type": assignment_type,
                "due_date": due_date,
            }
        )
        serializer.is_valid(raise_exception=True)

        assignment = Assignment.objects.create(
            course=course,
            title=title,
            description=description,
            type=assignment_type,
            total_marks=max(total_marks, 1),
            questions=questions if isinstance(questions, list) else [],
            rubric=rubric if isinstance(rubric, list) else [],
            due_date=serializer.validated_data["due_date"],
            status=AssignmentStatus.DRAFT,
            published_at=None,
        )

        return Response(AssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_201_CREATED)
