from django.conf import settings
from django.db import models

from apps.courses.models import Course


class ChatRole(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    ASSISTANT = "ASSISTANT", "Assistant"
    SYSTEM = "SYSTEM", "System"


class ChatMessage(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="chat_messages")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages", null=True, blank=True)
    role = models.CharField(max_length=20, choices=ChatRole.choices, default=ChatRole.STUDENT)
    message = models.TextField()
    ai_response = models.TextField(blank=True)
    sources = models.JSONField(default=list, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Feedback tracking for answer quality improvement
    feedback_score = models.IntegerField(null=True, blank=True)  # -1=unhelpful, 1=helpful
    feedback_text = models.TextField(blank=True)  # Why was it good/bad?
    feedback_timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("timestamp",)
        indexes = [
            models.Index(fields=['course', 'student', '-timestamp']),
            models.Index(fields=['course', '-timestamp']),
        ]
