from rest_framework import serializers

from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = (
            "id",
            "assignment",
            "student",
            "answers",
            "status",
            "submitted_at",
            "ai_grade",
            "ai_feedback",
            "score_breakdown",
            "grading_version",
            "graded_at",
        )
        read_only_fields = (
            "assignment",
            "student",
            "status",
            "submitted_at",
            "ai_grade",
            "ai_feedback",
            "score_breakdown",
            "grading_version",
            "graded_at",
        )
