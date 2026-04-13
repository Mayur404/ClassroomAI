from django.conf import settings
from django.db import models

from apps.courses.models import ClassSchedule, Course


class QuizMode(models.TextChoices):
    LIVE = "LIVE", "Live"
    PRACTICE = "PRACTICE", "Practice"


class QuizState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REVIEW = "REVIEW", "Review"
    PUBLISHED = "PUBLISHED", "Published"
    CLOSED = "CLOSED", "Closed"


class QuestionStatus(models.TextChoices):
    AI_GENERATED = "AI_GENERATED", "AI Generated"
    TEACHER_EDITED = "TEACHER_EDITED", "Teacher Edited"
    TEACHER_ADDED = "TEACHER_ADDED", "Teacher Added"


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    AUTO_SUBMITTED = "AUTO_SUBMITTED", "Auto Submitted"


class AlertType(models.TextChoices):
    LOW_SCORE = "LOW_SCORE", "Low Score"
    POOR_PERFORMANCE = "POOR_PERFORMANCE", "Poor Performance"


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    session = models.ForeignKey(ClassSchedule, on_delete=models.CASCADE, related_name="quizzes")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_quizzes")
    mode = models.CharField(max_length=20, choices=QuizMode.choices, default=QuizMode.LIVE)
    state = models.CharField(max_length=20, choices=QuizState.choices, default=QuizState.DRAFT)
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(blank=True, null=True)
    scheduled_for = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    due_at = models.DateTimeField(blank=True, null=True)
    is_private = models.BooleanField(default=False)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    low_score_threshold = models.PositiveIntegerField(default=60)
    source_material_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["course", "session", "state"]),
            models.Index(fields=["creator", "mode", "-created_at"]),
        ]


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    difficulty = models.CharField(max_length=20, default="MEDIUM")
    order_index = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=30, choices=QuestionStatus.choices, default=QuestionStatus.AI_GENERATED)
    source_citation = models.JSONField(default=dict, blank=True)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order_index", "id")
        indexes = [models.Index(fields=["quiz", "order_index"])]


class QuizOption(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="options")
    option_key = models.CharField(max_length=1)
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("option_key",)
        unique_together = ("question", "option_key")


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    status = models.CharField(max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS)
    score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    percentage = models.FloatField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    is_practice = models.BooleanField(default=False)
    feedback_released = models.BooleanField(default=False)

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["quiz", "student"]),
            models.Index(fields=["student", "-started_at"]),
        ]


class QuizAttemptAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="attempt_answers")
    selected_option_key = models.CharField(max_length=1, blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    marks_awarded = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("attempt", "question")


class QuizAlert(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quiz_alerts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="alerts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_alerts")
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=20, choices=AlertType.choices, default=AlertType.LOW_SCORE)
    threshold_percent = models.FloatField(default=60)
    actual_percent = models.FloatField(default=0)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["course", "is_read", "-created_at"])]
