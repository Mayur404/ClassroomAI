from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import extract_text_from_pdf, generate_schedule_from_course, parse_syllabus_content
from apps.assignments.models import Assignment
from apps.submissions.models import Submission

from .models import ClassSchedule, Course, Enrollment, ScheduleStatus
from .permissions import IsTeacher
from .serializers import ClassScheduleSerializer, CourseSerializer, EnrollmentSerializer, SyllabusUploadSerializer


class CourseListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "TEACHER":
            return Course.objects.filter(teacher=user).prefetch_related("schedule_items")
        return Course.objects.filter(enrollments__student=user).distinct().prefetch_related("schedule_items")

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class CourseDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CourseSerializer
    queryset = Course.objects.all().prefetch_related("schedule_items")


class EnrollmentCreateView(generics.CreateAPIView):
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.all()


class SyllabusUploadView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id) # Remove teacher check for simplified demo
        serializer = SyllabusUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("syllabus_pdf"):
            course.syllabus_pdf = serializer.validated_data["syllabus_pdf"]
            course.save()
            extracted_text = extract_text_from_pdf(course.syllabus_pdf.path)
            if extracted_text:
                course.syllabus_text = extracted_text

        raw_text = serializer.validated_data.get("syllabus_text") or course.syllabus_text or ""
        
        if not raw_text:
             return Response({"detail": "No syllabus text found to parse."}, status=status.HTTP_400_BAD_REQUEST)

        parsed = parse_syllabus_content(raw_text, course_id=course_id)
        if parsed.get("status") == "SUCCESS":
            course.syllabus_text = parsed["syllabus_text"]
            course.syllabus_parse_status = parsed["status"]
            course.num_assignments = parsed["num_assignments"]
            course.assignment_weightage = parsed["assignment_weightage"]
            course.extracted_topics = parsed["topics"]
            course.extracted_policies = parsed["policies"]
            course.parse_metadata = parsed["metadata"]
            
            # --- AUTO GENERATE SCHEDULE ---
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
                    duration_minutes=item["duration_minutes"]
                ) for item in schedule
            ])
            # ------------------------------
            
            course.save()
            return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)
        else:
             return Response({"detail": "AI Parsing failed", "error": parsed.get("error")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ScheduleGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id, teacher=request.user)
        course.schedule_items.all().delete()
        schedule = generate_schedule_from_course(course)
        ClassSchedule.objects.bulk_create(
            [
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
            ]
        )
        return Response(ClassScheduleSerializer(course.schedule_items.all(), many=True).data)


class ScheduleApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id, teacher=request.user)
        course.schedule_approved_at = timezone.now()
        course.status = "ACTIVE"
        course.save(update_fields=["schedule_approved_at", "status"])
        return Response({"approved": True, "schedule_approved_at": course.schedule_approved_at})


class ScheduleCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def post(self, request, schedule_id):
        schedule_item = ClassSchedule.objects.get(id=schedule_id, course__teacher=request.user)
        schedule_item.status = ScheduleStatus.COMPLETED
        schedule_item.save(update_fields=["status"])
        return Response(ClassScheduleSerializer(schedule_item).data)


class TeacherDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request):
        courses = Course.objects.filter(teacher=request.user)
        return Response(
            {
                "total_courses": courses.count(),
                "active_courses": courses.filter(status="ACTIVE").count(),
                "total_assignments": Assignment.objects.filter(course__teacher=request.user).count(),
                "total_submissions": Submission.objects.filter(assignment__course__teacher=request.user).count(),
            }
        )
