from django.conf import settings
from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


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
