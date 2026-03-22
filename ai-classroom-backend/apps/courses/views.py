from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import extract_text_from_pdf, generate_schedule_from_course
from apps.ai_service.rag_service import delete_material_chunks, index_course_materials
from apps.assignments.models import Assignment
from apps.submissions.models import Submission

from .models import ClassSchedule, Course, CourseMaterial, Enrollment, ScheduleStatus
from .permissions import IsTeacher
from .serializers import ClassScheduleSerializer, CourseSerializer, EnrollmentSerializer, SyllabusUploadSerializer


def _rebuild_schedule(course):
    """Delete existing schedule and regenerate from aggregated material topics."""
    course.schedule_items.all().delete()
    schedule = generate_schedule_from_course(course)
    ClassSchedule.objects.bulk_create([
        ClassSchedule(
            course=course,
            class_number=item["class_number"],
            order_index=item["class_number"],
            topic=item["topic"],
            subtopics=item["subtopics"],
            learning_objectives=item["learning_objectives"],
            duration_minutes=item["duration_minutes"],
        )
        for item in schedule
    ])


class CourseListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Course.objects.filter(teacher=self.request.user).prefetch_related("schedule_items", "materials")

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Course.objects.filter(teacher=self.request.user).prefetch_related("schedule_items", "materials")


class EnrollmentCreateView(generics.CreateAPIView):
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.all()


class SyllabusUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id, teacher=request.user)
        serializer = SyllabusUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        title = serializer.validated_data.get("title") or "Uploaded Material"
        uploaded_file = serializer.validated_data.get("syllabus_pdf")
        raw_text = serializer.validated_data.get("syllabus_text", "")

        # Create a CourseMaterial record
        material = CourseMaterial.objects.create(course=course, title=title)

        if uploaded_file:
            material.file = uploaded_file
            material.save(update_fields=["file"])
            raw_text = extract_text_from_pdf(material.file.path)

        if not raw_text:
            material.delete()
            return Response({"detail": "No text could be extracted."}, status=status.HTTP_400_BAD_REQUEST)

        material.content_text = raw_text

        # Index in ChromaDB (per-material)
        index_result = index_course_materials(course.id, material.id, raw_text)
        material.extracted_topics = index_result.get("topics", [])
        material.parse_status = "SUCCESS" if index_result["status"] == "SUCCESS" else "FAILED"
        material.save(update_fields=["content_text", "extracted_topics", "parse_status"])

        # Update course-level status
        course.syllabus_parse_status = "SUCCESS"
        course.save(update_fields=["syllabus_parse_status"])

        # Rebuild schedule from aggregated topics
        _rebuild_schedule(course)

        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class MaterialDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, material_id):
        material = CourseMaterial.objects.get(id=material_id, course__teacher=request.user)
        course = material.course

        # Remove vectors from ChromaDB
        delete_material_chunks(course.id, material.id)
        material.delete()

        # Refresh course state
        if course.materials.exists():
            course.syllabus_parse_status = "SUCCESS"
        else:
            course.syllabus_parse_status = "PENDING"
        course.save(update_fields=["syllabus_parse_status"])

        # Rebuild schedule
        _rebuild_schedule(course)

        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class ScheduleGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id, teacher=request.user)
        _rebuild_schedule(course)
        return Response(ClassScheduleSerializer(course.schedule_items.all(), many=True).data)


class ScheduleApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id, teacher=request.user)
        course.schedule_approved_at = timezone.now()
        course.status = "ACTIVE"
        course.save(update_fields=["schedule_approved_at", "status"])
        return Response({"approved": True, "schedule_approved_at": course.schedule_approved_at})


class ScheduleCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, schedule_id):
        schedule_item = ClassSchedule.objects.get(id=schedule_id, course__teacher=request.user)
        schedule_item.status = ScheduleStatus.COMPLETED
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
