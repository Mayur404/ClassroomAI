from django.db import models

from apps.courses.models import Course


class AssignmentType(models.TextChoices):
    MCQ = "MCQ", "MCQ"
    ESSAY = "ESSAY", "Essay"
    CODING = "CODING", "Coding"


class AssignmentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"
    CLOSED = "CLOSED", "Closed"


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=AssignmentType.choices)
    status = models.CharField(max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.DRAFT)
    total_marks = models.PositiveIntegerField(default=20)
    questions = models.JSONField(default=list)
    rubric = models.JSONField(default=list, blank=True)
    answer_key = models.JSONField(default=dict, blank=True)
    due_date = models.DateTimeField()
    covered_until_class = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)
