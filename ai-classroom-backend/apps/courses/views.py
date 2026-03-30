import logging
import time

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import (
    extract_pdf_content,
    generate_schedule_from_course,
    summarize_course_materials,
)
from apps.ai_service.rag_service import delete_material_chunks, index_course_materials
from apps.ai_service.enhanced_rag import index_material_with_structure
from apps.assignments.models import Assignment
from apps.submissions.models import Submission

from .models import ClassSchedule, Course, CourseMaterial, Enrollment, ParseStatus, ScheduleStatus
from .serializers import ClassScheduleSerializer, CourseSerializer, EnrollmentSerializer, SyllabusUploadSerializer

logger = logging.getLogger(__name__)


def _humanize_bytes(size: int | None) -> str:
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f} {units[unit_index]}"


def _sync_course_summary(course, latest_index_result=None):
    summary = summarize_course_materials(course)

    materials = list(course.materials.all())
    if not materials:
        parse_status = ParseStatus.PENDING
    elif any(material.parse_status == ParseStatus.SUCCESS for material in materials):
        parse_status = ParseStatus.SUCCESS
    else:
        parse_status = ParseStatus.FAILED

    parse_metadata = summary["parse_metadata"]
    if latest_index_result:
        parse_metadata["last_index_status"] = latest_index_result.get("status")
        parse_metadata["embedding_backend"] = latest_index_result.get("embedding_backend")
        if latest_index_result.get("warning"):
            parse_metadata["warning"] = latest_index_result["warning"]
        if latest_index_result.get("extraction"):
            parse_metadata["last_extraction"] = latest_index_result["extraction"]

    course.extracted_topics = summary["topics"]
    course.extracted_policies = summary["policies"]
    course.num_assignments = summary["recommended_num_assignments"]
    course.assignment_weightage = summary["assignment_weightage"]
    course.parse_metadata = parse_metadata
    course.syllabus_parse_status = parse_status
    course.save(
        update_fields=[
            "extracted_topics",
            "extracted_policies",
            "num_assignments",
            "assignment_weightage",
            "parse_metadata",
            "syllabus_parse_status",
        ]
    )
    return summary


def _rebuild_schedule(course, latest_index_result=None, *, use_ai: bool = False):
    """Delete existing schedule and regenerate from aggregated material topics."""
    started_at = time.perf_counter()
    existing_status_by_topic = {
        (schedule_item.topic or "").strip().lower(): schedule_item.status
        for schedule_item in course.schedule_items.all()
    }
    course.schedule_items.all().delete()
    summary = _sync_course_summary(course, latest_index_result=latest_index_result)
    if not summary["topics"]:
        logger.info("Skipping schedule rebuild for course %s because no topics were extracted", course.id)
        return

    logger.info(
        "Rebuilding schedule for course %s using %s topics mode=%s",
        course.id,
        len(summary["topics"]),
        "ai" if use_ai else "fast",
    )
    schedule = generate_schedule_from_course(
        course,
        blueprints=summary["schedule_blueprints"],
        use_ai=use_ai,
    )
    ClassSchedule.objects.bulk_create([
        ClassSchedule(
            course=course,
            class_number=item["class_number"],
            order_index=item["class_number"],
            topic=item["topic"],
            subtopics=item["subtopics"],
            learning_objectives=item["learning_objectives"],
            duration_minutes=item["duration_minutes"],
            status=existing_status_by_topic.get((item["topic"] or "").strip().lower(), ScheduleStatus.PLANNED),
            is_ai_generated=use_ai,
        )
        for item in schedule
    ])
    logger.info(
        "Schedule rebuild completed for course %s with %s classes mode=%s duration=%.2fs",
        course.id,
        len(schedule),
        "ai" if use_ai else "fast",
        time.perf_counter() - started_at,
    )


class CourseListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Course.objects.filter(teacher=self.request.user)
            .select_related("teacher")
            .annotate(assignment_count_value=Count("assignments", distinct=True))
            .prefetch_related("schedule_items", "materials")
        )

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Course.objects.filter(teacher=self.request.user)
            .select_related("teacher")
            .annotate(assignment_count_value=Count("assignments", distinct=True))
            .prefetch_related("schedule_items", "materials")
        )


class EnrollmentCreateView(generics.CreateAPIView):
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.all()
    permission_classes = [permissions.IsAuthenticated]


class SyllabusUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        serializer = SyllabusUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        title = serializer.validated_data.get("title") or "Uploaded Material"
        uploaded_file = serializer.validated_data.get("syllabus_pdf")
        raw_text = serializer.validated_data.get("syllabus_text", "")

        with transaction.atomic():
            material = CourseMaterial.objects.create(
                course=course, 
                title=title,
                parse_status=ParseStatus.PENDING
            )

            if uploaded_file:
                material.file = uploaded_file
                material.save(update_fields=["file"])
                
                # Run extraction and indexing synchronously (Blocking)
                from apps.background_logic import extract_pdf_logic
                extract_pdf_logic(material.id, material.file.path)
                
                logger.info("Finished synchronous extraction for material=%s", material.id)
            elif raw_text:
                material.content_text = raw_text
                material.save(update_fields=["content_text"])
                
                # Run indexing synchronously (Blocking)
                from apps.background_logic import index_material_logic
                index_material_logic(material.id)
                
                logger.info("Finished synchronous indexing for material=%s", material.id)
            else:
                material.delete()
                return Response(
                    {"detail": "No content provided (file or text required)."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Re-fetch course to get updated materials and statuses
        course.refresh_from_db()
        
        # Rebuild schedule and update course summary
        _rebuild_schedule(course, use_ai=False)
        
        # Return the course - processing is already done
        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class MaterialDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, material_id):
        material = get_object_or_404(CourseMaterial, id=material_id, course__teacher=request.user)
        course = material.course

        with transaction.atomic():
            delete_material_chunks(course.id, material.id)
            material.delete()
            _rebuild_schedule(course, use_ai=False)

        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class ScheduleGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        _rebuild_schedule(course, use_ai=True)
        return Response(ClassScheduleSerializer(course.schedule_items.all(), many=True).data)


class ScheduleApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        course.schedule_approved_at = timezone.now()
        course.status = "ACTIVE"
        course.save(update_fields=["schedule_approved_at", "status"])
        return Response({"approved": True, "schedule_approved_at": course.schedule_approved_at})


class ScheduleCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, schedule_id):
        schedule_item = get_object_or_404(ClassSchedule, id=schedule_id, course__teacher=request.user)
        completed = request.data.get("completed", True)
        if isinstance(completed, str):
            completed = completed.strip().lower() not in {"false", "0", "no"}

        schedule_item.status = ScheduleStatus.COMPLETED if completed else ScheduleStatus.PLANNED
        schedule_item.save(update_fields=["status"])
        return Response(ClassScheduleSerializer(schedule_item).data)


class TeacherDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        courses = Course.objects.filter(teacher=request.user)
        return Response({
            "total_courses": courses.count(),
            "active_courses": courses.filter(status="ACTIVE").count(),
            "total_assignments": Assignment.objects.filter(course__teacher=request.user).count(),
            "total_submissions": Submission.objects.filter(assignment__course__teacher=request.user).count(),
        })
