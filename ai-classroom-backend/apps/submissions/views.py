from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import grade_submission
from apps.assignments.models import Assignment
from apps.assignments.models import AssignmentStatus

from .models import Submission, SubmissionStatus
from .serializers import SubmissionSerializer, SubmissionTeacherGradeSerializer


class SubmissionCreateView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, assignment_id):
        if request.user.role != "STUDENT":
            raise PermissionDenied("Only students can submit assignments.")
        assignment = get_object_or_404(
            Assignment.objects.select_related("course"),
            id=assignment_id,
            course__enrollments__student=request.user,
        )
        if assignment.status != AssignmentStatus.PUBLISHED:
            return Response({"detail": "This assignment is not published yet."}, status=status.HTTP_400_BAD_REQUEST)
        if assignment.due_date and assignment.due_date <= timezone.now():
            return Response({"detail": "This assignment is closed because the due date has passed."}, status=status.HTTP_400_BAD_REQUEST)
        if Submission.objects.filter(assignment=assignment, student=request.user).exists():
            return Response(
                {"detail": "You have already submitted this assignment. Retakes are disabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = SubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answers = serializer.validated_data.get("answers", {})
        result = grade_submission(assignment=assignment, answers=answers)

        submission = Submission.objects.create(
            assignment=assignment,
            student=request.user,
            answers=answers,
            status=SubmissionStatus.GRADED,
            submitted_at=timezone.now(),
            ai_grade=result["total_score"],
            ai_feedback=result.get("ai_feedback", {"overall_feedback": result["overall_feedback"]}),
            score_breakdown=result["score_breakdown"],
            grading_version=result.get("grading_version", "v1"),
            graded_at=timezone.now(),
        )
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Submission.objects.filter(
            Q(student=self.request.user) | Q(assignment__course__teacher=self.request.user)
        ).select_related("assignment", "student", "assignment__course")

    def destroy(self, request, *args, **kwargs):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Students cannot delete submitted assignments.")
        submission = self.get_object()
        if submission.assignment.course.teacher_id != request.user.id:
            raise PermissionDenied("Only the classroom teacher can delete submissions.")
        return super().destroy(request, *args, **kwargs)


class SubmissionRegradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, submission_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can regrade submissions.")
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=submission_id,
            assignment__course__teacher=request.user,
        )
        result = grade_submission(assignment=submission.assignment, answers=submission.answers)
        submission.ai_grade = result["total_score"]
        submission.ai_feedback = result.get("ai_feedback", {"overall_feedback": result["overall_feedback"]})
        submission.score_breakdown = result["score_breakdown"]
        submission.grading_version = result.get("grading_version", submission.grading_version)
        submission.status = SubmissionStatus.GRADED
        submission.graded_at = timezone.now()
        submission.save(update_fields=["ai_grade", "ai_feedback", "score_breakdown", "grading_version", "status", "graded_at"])
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)


class SubmissionTeacherGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, submission_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can override assignment marks.")
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=submission_id,
            assignment__course__teacher=request.user,
        )
        serializer = SubmissionTeacherGradeSerializer(data=request.data, context={"submission": submission})
        serializer.is_valid(raise_exception=True)

        submission.teacher_grade = serializer.validated_data["teacher_grade"]
        submission.teacher_feedback = serializer.validated_data.get("teacher_feedback", "").strip()
        submission.teacher_graded_at = timezone.now()
        submission.status = SubmissionStatus.GRADED
        submission.save(update_fields=["teacher_grade", "teacher_feedback", "teacher_graded_at", "status"])
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)


class SubmissionPrecheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, assignment_id):
        if request.user.role != "STUDENT":
            raise PermissionDenied("Only students can pre-check submissions.")
        assignment = get_object_or_404(
            Assignment.objects.select_related("course"),
            id=assignment_id,
            course__enrollments__student=request.user,
        )
        if assignment.status != AssignmentStatus.PUBLISHED:
            return Response({"detail": "This assignment is not published yet."}, status=status.HTTP_400_BAD_REQUEST)
        if assignment.due_date and assignment.due_date <= timezone.now():
            return Response({"detail": "This assignment is closed because the due date has passed."}, status=status.HTTP_400_BAD_REQUEST)
        answers = request.data.get("answers", {})
        if not isinstance(answers, dict) or not answers:
            return Response({"detail": "answers must be a non-empty object"}, status=status.HTTP_400_BAD_REQUEST)

        result = grade_submission(assignment=assignment, answers=answers)
        return Response(
            {
                "preview": True,
                "assignment_id": assignment.id,
                "total_score": result.get("total_score", 0),
                "overall_feedback": result.get("overall_feedback", ""),
                "score_breakdown": result.get("score_breakdown", []),
                "ai_feedback": result.get("ai_feedback", {}),
            },
            status=status.HTTP_200_OK,
        )
