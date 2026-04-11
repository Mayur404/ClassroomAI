from datetime import datetime, time

from django.utils import timezone
from rest_framework import serializers

from apps.submissions.serializers import SubmissionSerializer

from .models import Assignment


class AssignmentSerializer(serializers.ModelSerializer):
    grade = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    teacher_submission_summary = serializers.SerializerMethodField()
    class_submissions = serializers.SerializerMethodField()
    is_past_due = serializers.SerializerMethodField()

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
            "assignment_pdf",
            "due_date",
            "covered_until_class",
            "created_at",
            "published_at",
            "grade",
            "latest_submission",
            "question_count",
            "teacher_submission_summary",
            "class_submissions",
            "is_past_due",
        )
        read_only_fields = (
            "created_at",
            "published_at",
            "grade",
            "latest_submission",
            "question_count",
            "teacher_submission_summary",
            "class_submissions",
            "is_past_due",
        )

    def _request_user(self):
        request = self.context.get("request")
        if not request:
            return None
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        return user

    def _is_teacher_view(self, obj):
        user = self._request_user()
        return bool(user and getattr(user, "role", None) == "TEACHER" and obj.course.teacher_id == user.id)

    def _latest_submission_for_request_user(self, obj):
        user = self._request_user()
        if not user:
            return None

        prefetched = getattr(obj, "request_user_submissions", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None

        return obj.submissions.filter(student=user).order_by("-submitted_at").first()

    def _teacher_visible_submissions(self, obj):
        if not self._is_teacher_view(obj):
            return []

        prefetched = getattr(obj, "teacher_visible_submissions", None)
        if prefetched is not None:
            return prefetched

        return obj.submissions.select_related("student", "assignment").order_by("-submitted_at")

    def get_grade(self, obj):
        submission = self._latest_submission_for_request_user(obj)
        if not submission:
            return None
        return {"score": submission.final_grade, "out_of": obj.total_marks}

    def get_latest_submission(self, obj):
        submission = self._latest_submission_for_request_user(obj)
        if not submission:
            return None

        return SubmissionSerializer(submission).data

    def get_question_count(self, obj):
        return len(obj.questions or [])

    def get_teacher_submission_summary(self, obj):
        if not self._is_teacher_view(obj):
            return None

        submissions = list(self._teacher_visible_submissions(obj))
        submitted_count = getattr(obj, "submission_count_value", len(submissions))
        total_students = getattr(obj, "enrollment_count_value", None)
        if total_students is None:
            total_students = obj.course.enrollments.count()

        average_score = getattr(obj, "average_score_value", None)
        if average_score is None and submissions:
            average_score = sum(float(item.final_grade or 0) for item in submissions) / len(submissions)

        return {
            "submitted_count": submitted_count,
            "total_students": total_students,
            "pending_count": max(int(total_students) - int(submitted_count), 0),
            "average_score": round(float(average_score), 2) if average_score is not None else None,
        }

    def get_class_submissions(self, obj):
        if not self._is_teacher_view(obj):
            return []
        return SubmissionSerializer(self._teacher_visible_submissions(obj), many=True).data

    def get_is_past_due(self, obj):
        due_date = getattr(obj, "due_date", None)
        if not due_date:
            return False
        return due_date <= timezone.now()


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
