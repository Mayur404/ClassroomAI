from django.conf import settings
from django.db import models

from apps.assignments.models import Assignment


class SubmissionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    GRADED = "GRADED", "Graded"


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    answers = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    ai_grade = models.FloatField(default=0)
    ai_feedback = models.JSONField(default=dict, blank=True)
    score_breakdown = models.JSONField(default=list, blank=True)
    grading_version = models.CharField(max_length=50, default="v1")
    teacher_grade = models.FloatField(blank=True, null=True)
    teacher_feedback = models.TextField(blank=True)
    teacher_graded_at = models.DateTimeField(blank=True, null=True)
    graded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-submitted_at",)
        unique_together = ("assignment", "student")
        indexes = [
            models.Index(fields=['assignment', '-submitted_at']),
            models.Index(fields=['student', '-submitted_at']),
        ]

    @property
    def final_grade(self):
        return self.teacher_grade if self.teacher_grade is not None else self.ai_grade

    @property
    def grade_source(self):
        return "TEACHER" if self.teacher_grade is not None else "AI"
