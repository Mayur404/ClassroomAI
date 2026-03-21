from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import grade_submission
from apps.assignments.models import Assignment
from apps.courses.permissions import IsStudent, IsTeacher

from .models import Submission, SubmissionStatus
from .serializers import SubmissionSerializer


class SubmissionCreateView(generics.CreateAPIView):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        assignment = Assignment.objects.get(id=self.kwargs["assignment_id"])
        result = grade_submission(assignment=assignment, answers=self.request.data.get("answers", {}))
        if self.request.user.is_authenticated:
            student = self.request.user
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            student, _ = User.objects.get_or_create(email="demo@student.com", defaults={"name": "Demo Student"})

        serializer.save(
            assignment=assignment,
            student=student,
            status=SubmissionStatus.GRADED,
            ai_grade=result["total_score"],
            ai_feedback={"overall_feedback": result["overall_feedback"]},
            score_breakdown=result["score_breakdown"],
            graded_at=timezone.now(),
        )


class SubmissionDetailView(generics.RetrieveAPIView):
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.all()


class SubmissionRegradeView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, submission_id):
        submission = Submission.objects.get(id=submission_id, assignment__course__teacher=request.user)
        result = grade_submission(assignment=submission.assignment, answers=submission.answers)
        submission.ai_grade = result["total_score"]
        submission.ai_feedback = {"overall_feedback": result["overall_feedback"]}
        submission.score_breakdown = result["score_breakdown"]
        submission.graded_at = timezone.now()
        submission.save(update_fields=["ai_grade", "ai_feedback", "score_breakdown", "graded_at"])
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)
