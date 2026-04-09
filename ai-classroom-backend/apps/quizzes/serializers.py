from django.db import transaction
from rest_framework import serializers

from .models import (
    AttemptStatus,
    Quiz,
    QuizAlert,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizMode,
    QuizOption,
    QuizQuestion,
    QuizState,
    QuestionStatus,
)


class QuizOptionTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ("id", "option_key", "option_text", "is_correct")


class QuizOptionStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ("id", "option_key", "option_text")


class QuizQuestionTeacherSerializer(serializers.ModelSerializer):
    options = QuizOptionTeacherSerializer(many=True)

    class Meta:
        model = QuizQuestion
        fields = (
            "id",
            "question_text",
            "difficulty",
            "order_index",
            "status",
            "source_citation",
            "explanation",
            "options",
        )

    def validate_options(self, value):
        if len(value) != 4:
            raise serializers.ValidationError("Each question must have exactly 4 options.")
        keys = {str(item.get("option_key", "")).strip().upper() for item in value}
        if keys != {"A", "B", "C", "D"}:
            raise serializers.ValidationError("Option keys must be A, B, C, D.")
        correct_count = sum(1 for item in value if item.get("is_correct"))
        if correct_count != 1:
            raise serializers.ValidationError("Exactly one option must be marked correct.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.status = QuestionStatus.TEACHER_EDITED
        instance.save()

        if options_data is not None:
            existing = {opt.option_key: opt for opt in instance.options.all()}
            for option in options_data:
                key = option["option_key"]
                opt_obj = existing.get(key)
                if opt_obj:
                    opt_obj.option_text = option["option_text"]
                    opt_obj.is_correct = option["is_correct"]
                    opt_obj.save(update_fields=["option_text", "is_correct"])
        return instance


class QuizQuestionStudentSerializer(serializers.ModelSerializer):
    options = QuizOptionStudentSerializer(many=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "question_text", "difficulty", "order_index", "options")


class QuizTeacherSerializer(serializers.ModelSerializer):
    questions = QuizQuestionTeacherSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course",
            "session",
            "creator",
            "mode",
            "state",
            "title",
            "instructions",
            "time_limit_minutes",
            "published_at",
            "due_at",
            "is_private",
            "low_score_threshold",
            "source_material_snapshot",
            "questions",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("creator", "published_at", "source_material_snapshot", "created_at", "updated_at")


class QuizStudentSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course",
            "session",
            "mode",
            "state",
            "title",
            "instructions",
            "time_limit_minutes",
            "due_at",
            "is_private",
            "questions",
            "created_at",
        )

    def get_questions(self, obj):
        include = bool(self.context.get("include_questions", False))
        if not include:
            return []
        return QuizQuestionStudentSerializer(obj.questions.all(), many=True).data


class QuizGenerateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    instructions = serializers.CharField(required=False, allow_blank=True)
    question_count = serializers.IntegerField(min_value=3, max_value=25, required=False, default=8)
    time_limit_minutes = serializers.IntegerField(min_value=1, max_value=180, required=False)
    due_at = serializers.DateTimeField(required=False)
    low_score_threshold = serializers.IntegerField(min_value=1, max_value=100, required=False, default=60)
    module_scope = serializers.ChoiceField(choices=("single", "multiple", "all"), required=False, default="single")
    session_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=True)
    include_all_modules = serializers.BooleanField(required=False, default=False)


class QuizQuestionCreateSerializer(serializers.Serializer):
    question_text = serializers.CharField()
    difficulty = serializers.CharField(required=False, default="MEDIUM")
    explanation = serializers.CharField(required=False, allow_blank=True)
    options = QuizOptionTeacherSerializer(many=True)


class AttemptStartSerializer(serializers.Serializer):
    pass


class AttemptAnswerUpsertSerializer(serializers.Serializer):
    answers = serializers.DictField(child=serializers.CharField(allow_blank=True), allow_empty=False)


class AttemptSubmitSerializer(serializers.Serializer):
    answers = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)


class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "quiz",
            "student",
            "status",
            "score",
            "max_score",
            "percentage",
            "started_at",
            "submitted_at",
            "is_practice",
            "feedback_released",
        )
        read_only_fields = (
            "student",
            "status",
            "score",
            "max_score",
            "percentage",
            "submitted_at",
            "feedback_released",
        )


class QuizAlertSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)

    class Meta:
        model = QuizAlert
        fields = (
            "id",
            "course",
            "quiz",
            "student",
            "student_name",
            "attempt",
            "alert_type",
            "threshold_percent",
            "actual_percent",
            "is_read",
            "created_at",
        )
