from django.db import transaction
import random
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
    options = serializers.SerializerMethodField()

    class Meta:
        model = QuizQuestion
        fields = ("id", "question_text", "difficulty", "order_index", "options")

    def get_options(self, obj):
        options = list(obj.options.all())
        student_id = self.context.get("student_id")
        quiz_id = self.context.get("quiz_id")
        should_shuffle = bool(self.context.get("shuffle_options", False))
        if should_shuffle and student_id and quiz_id:
            rng = random.Random(f"{quiz_id}:{student_id}:{obj.id}:options")
            rng.shuffle(options)
        return QuizOptionStudentSerializer(options, many=True).data


class QuizTeacherSerializer(serializers.ModelSerializer):
    questions = QuizQuestionTeacherSerializer(many=True, read_only=True)
    question_count = serializers.SerializerMethodField()

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
            "scheduled_for",
            "published_at",
            "due_at",
            "is_private",
            "shuffle_questions",
            "shuffle_options",
            "low_score_threshold",
            "source_material_snapshot",
            "question_count",
            "questions",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("creator", "published_at", "source_material_snapshot", "created_at", "updated_at")

    def validate(self, attrs):
        scheduled_for = attrs.get("scheduled_for", getattr(self.instance, "scheduled_for", None))
        due_at = attrs.get("due_at", getattr(self.instance, "due_at", None))
        if scheduled_for and due_at and due_at <= scheduled_for:
            raise serializers.ValidationError("Due time must be after scheduled time.")
        return attrs

    def get_question_count(self, obj):
        annotated = getattr(obj, "question_count_value", None)
        if annotated is not None:
            return int(annotated)
        return obj.questions.count()


class QuizStudentSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()

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
            "scheduled_for",
            "due_at",
            "is_private",
            "question_count",
            "questions",
            "created_at",
        )

    def get_questions(self, obj):
        include = bool(self.context.get("include_questions", False))
        if not include:
            return []
        student_id = self.context.get("student_id")
        questions = list(obj.questions.all())

        if bool(obj.shuffle_questions) and student_id:
            rng = random.Random(f"{obj.id}:{student_id}:questions")
            rng.shuffle(questions)

        payload = QuizQuestionStudentSerializer(
            questions,
            many=True,
            context={
                "student_id": student_id,
                "quiz_id": obj.id,
                "shuffle_options": bool(obj.shuffle_options),
            },
        ).data

        for idx, item in enumerate(payload, start=1):
            item["order_index"] = idx
        return payload

    def get_question_count(self, obj):
        annotated = getattr(obj, "question_count_value", None)
        if annotated is not None:
            return int(annotated)
        return obj.questions.count()


class QuizGenerateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    instructions = serializers.CharField(required=False, allow_blank=True)
    question_count = serializers.IntegerField(min_value=3, max_value=25, required=False, default=8)
    time_limit_minutes = serializers.IntegerField(min_value=1, max_value=180, required=False)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    due_at = serializers.DateTimeField(required=False)
    shuffle_questions = serializers.BooleanField(required=False, default=True)
    shuffle_options = serializers.BooleanField(required=False, default=True)
    low_score_threshold = serializers.IntegerField(min_value=1, max_value=100, required=False, default=60)
    module_scope = serializers.ChoiceField(choices=("single", "multiple", "all"), required=False, default="single")
    session_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=True)
    include_all_modules = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        scheduled_for = attrs.get("scheduled_for")
        due_at = attrs.get("due_at")
        if scheduled_for and due_at and due_at <= scheduled_for:
            raise serializers.ValidationError("Due time must be after scheduled time.")
        return attrs


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
    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    alert_type_label = serializers.CharField(source="get_alert_type_display", read_only=True)

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
            "alert_type_label",
            "quiz_title",
            "threshold_percent",
            "actual_percent",
            "is_read",
            "created_at",
        )
