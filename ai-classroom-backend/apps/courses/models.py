from django.conf import settings
from django.db import models
import secrets
import string


class CourseStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


class ParseStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class ScheduleStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    COMPLETED = "COMPLETED", "Completed"


def syllabus_upload_path(instance, filename):
    return f"syllabi/course_{instance.id}/{filename}"


class Course(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses_taught")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=CourseStatus.choices, default=CourseStatus.DRAFT)
    syllabus_pdf = models.FileField(upload_to=syllabus_upload_path, blank=True, null=True)
    syllabus_text = models.TextField(blank=True)
    syllabus_parse_status = models.CharField(max_length=20, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    num_assignments = models.PositiveIntegerField(default=2)
    assignment_weightage = models.CharField(max_length=100, blank=True)
    extracted_topics = models.JSONField(default=list, blank=True)
    extracted_policies = models.JSONField(default=list, blank=True)
    parse_metadata = models.JSONField(default=dict, blank=True)
    schedule_approved_at = models.DateTimeField(blank=True, null=True)
    invite_code = models.CharField(max_length=6, unique=True, editable=False, db_index=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['teacher']),
            models.Index(fields=['status']),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.invite_code:
            alphabet = string.ascii_uppercase + string.digits
            for _ in range(12):
                candidate = "".join(secrets.choice(alphabet) for _ in range(6))
                if not Course.objects.filter(invite_code=candidate).exists():
                    self.invite_code = candidate
                    break
        super().save(*args, **kwargs)


def material_upload_path(instance, filename):
    return f"materials/course_{instance.course_id}/{filename}"


class CourseMaterial(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=255, default="Uploaded Material")
    file = models.FileField(upload_to=material_upload_path, blank=True, null=True)
    content_text = models.TextField(blank=True)
    extracted_topics = models.JSONField(default=list, blank=True)
    parse_status = models.CharField(max_length=20, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=['course', '-created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.course.name})"


class Enrollment(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course")


class ClassSchedule(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="schedule_items")
    order_index = models.PositiveIntegerField()
    class_number = models.PositiveIntegerField()
    topic = models.CharField(max_length=255)
    subtopics = models.JSONField(default=list, blank=True)
    learning_objectives = models.JSONField(default=list, blank=True)
    duration_minutes = models.PositiveIntegerField(default=90)
    status = models.CharField(max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.PLANNED)
    is_ai_generated = models.BooleanField(default=True)

    class Meta:
        ordering = ("class_number", "order_index")
        unique_together = ("course", "class_number")


class StudentNotebook(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="student_notebooks")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="private_notebooks")
    title = models.CharField(max_length=255, default="Personal Notes")
    content_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["course", "student", "-updated_at"]),
        ]


class StudentFlashcard(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="flashcards")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="flashcards")
    question = models.TextField()
    answer = models.TextField()
    ease_factor = models.FloatField(default=2.5)
    interval_days = models.PositiveIntegerField(default=0)
    repetitions = models.PositiveIntegerField(default=0)
    due_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("due_at",)
        indexes = [
            models.Index(fields=["course", "student", "due_at"]),
        ]
