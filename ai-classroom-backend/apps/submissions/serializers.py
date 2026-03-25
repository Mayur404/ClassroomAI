from rest_framework import serializers

from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    def validate_answers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("answers must be an object keyed by question number.")

        normalized = {}
        for key, answer in value.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                raise serializers.ValidationError("Each answer must have a question number key.")

            if isinstance(answer, list):
                text_value = ", ".join(str(item).strip() for item in answer if str(item).strip())
            elif answer is None:
                text_value = ""
            else:
                text_value = str(answer).strip()

            if len(text_value) > 5000:
                raise serializers.ValidationError("Each answer must be 5000 characters or fewer.")

            normalized[normalized_key] = text_value

        return normalized

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
