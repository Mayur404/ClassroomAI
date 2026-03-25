from datetime import datetime, time

from django.utils import timezone
from rest_framework import serializers

from .models import Assignment


class AssignmentSerializer(serializers.ModelSerializer):
    grade = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "course",
            "title",
            "description",
            "type",
            "status",
            "total_marks",
            "questions",
            "rubric",
            "answer_key",
            "due_date",
            "covered_until_class",
            "created_at",
            "published_at",
            "grade",
            "latest_submission",
        )
        read_only_fields = ("status", "created_at", "published_at", "grade", "latest_submission")

    def _latest_submission_for_request_user(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not request or not user or not user.is_authenticated:
            return None

        prefetched = getattr(obj, "request_user_submissions", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None

        return obj.submissions.filter(student=user).order_by("-submitted_at").first()

    def get_grade(self, obj):
        submission = self._latest_submission_for_request_user(obj)
        if not submission:
            return None
        return {"score": submission.ai_grade, "out_of": obj.total_marks}

    def get_latest_submission(self, obj):
        submission = self._latest_submission_for_request_user(obj)
        if not submission:
            return None

        return {
            "id": submission.id,
            "answers": submission.answers,
            "status": submission.status,
            "submitted_at": submission.submitted_at,
            "ai_grade": submission.ai_grade,
            "ai_feedback": submission.ai_feedback,
            "score_breakdown": submission.score_breakdown,
            "graded_at": submission.graded_at,
        }


class FlexibleDateTimeField(serializers.DateTimeField):
    """Accept both ISO datetimes and date-only strings from the current frontend."""

    def to_internal_value(self, value):
        if isinstance(value, str) and "T" not in value:
            parsed_date = serializers.DateField().to_internal_value(value)
            combined = datetime.combine(parsed_date, time(hour=23, minute=59, second=59))
            return timezone.make_aware(combined, timezone.get_current_timezone())
        return super().to_internal_value(value)


class AssignmentGenerateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    type = serializers.ChoiceField(choices=("MCQ", "ESSAY", "CODING"))
    due_date = FlexibleDateTimeField()
