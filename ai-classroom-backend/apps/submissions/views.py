from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import grade_submission
from apps.assignments.models import Assignment

from .models import Submission, SubmissionStatus
from .serializers import SubmissionSerializer


class SubmissionCreateView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(
            Assignment.objects.select_related("course"),
            id=assignment_id,
            course__teacher=request.user,
        )
        serializer = SubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answers = serializer.validated_data.get("answers", {})
        result = grade_submission(assignment=assignment, answers=answers)

        submission, created = Submission.objects.update_or_create(
            assignment=assignment,
            student=request.user,
            defaults={
                "answers": answers,
                "status": SubmissionStatus.GRADED,
                "submitted_at": timezone.now(),
                "ai_grade": result["total_score"],
                "ai_feedback": result.get("ai_feedback", {"overall_feedback": result["overall_feedback"]}),
                "score_breakdown": result["score_breakdown"],
                "graded_at": timezone.now(),
            },
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(SubmissionSerializer(submission).data, status=response_status)


class SubmissionDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Submission.objects.filter(
            Q(student=self.request.user) | Q(assignment__course__teacher=self.request.user)
        ).select_related("assignment", "student", "assignment__course")


class SubmissionRegradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, submission_id):
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=submission_id,
            assignment__course__teacher=request.user,
        )
        result = grade_submission(assignment=submission.assignment, answers=submission.answers)
        submission.ai_grade = result["total_score"]
        submission.ai_feedback = result.get("ai_feedback", {"overall_feedback": result["overall_feedback"]})
        submission.score_breakdown = result["score_breakdown"]
        submission.status = SubmissionStatus.GRADED
        submission.graded_at = timezone.now()
        submission.save(update_fields=["ai_grade", "ai_feedback", "score_breakdown", "status", "graded_at"])
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)
