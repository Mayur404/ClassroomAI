from rest_framework import serializers

from .models import (
    ClassSchedule,
    Course,
    CourseAnnouncement,
    CourseMaterial,
    Enrollment,
    ScheduleStatus,
    StudentFlashcard,
    StudentNotebook,
)


class ClassScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassSchedule
        fields = (
            "id",
            "course",
            "class_number",
            "order_index",
            "topic",
            "subtopics",
            "learning_objectives",
            "duration_minutes",
            "status",
            "is_ai_generated",
        )
        read_only_fields = ("course",)


class CourseMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseMaterial
        fields = ("id", "title", "file", "content_text", "extracted_topics", "parse_status", "created_at")


class CourseAnnouncementSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)

    class Meta:
        model = CourseAnnouncement
        fields = ("id", "course", "teacher", "teacher_name", "title", "message", "created_at", "updated_at")
        read_only_fields = ("course", "teacher", "teacher_name", "created_at", "updated_at")


class CourseSerializer(serializers.ModelSerializer):
    schedule_items = ClassScheduleSerializer(many=True, read_only=True)
    materials = CourseMaterialSerializer(many=True, read_only=True)
    announcements = CourseAnnouncementSerializer(many=True, read_only=True)
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)
    assignment_count = serializers.SerializerMethodField()
    completed_class_count = serializers.SerializerMethodField()
    schedule_progress_percent = serializers.SerializerMethodField()
    next_class_topic = serializers.SerializerMethodField()
    material_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "teacher",
            "teacher_name",
            "name",
            "description",
            "status",
            "syllabus_pdf",
            "syllabus_text",
            "syllabus_parse_status",
            "materials",
            "announcements",
            "num_assignments",
            "assignment_weightage",
            "extracted_topics",
            "extracted_policies",
            "parse_metadata",
            "schedule_approved_at",
            "invite_code",
            "created_at",
            "assignment_count",
            "completed_class_count",
            "schedule_progress_percent",
            "next_class_topic",
            "material_count",
            "schedule_items",
        )
        read_only_fields = (
            "teacher",
            "syllabus_text",
            "syllabus_parse_status",
            "extracted_topics",
            "extracted_policies",
            "parse_metadata",
            "schedule_approved_at",
            "invite_code",
            "created_at",
            "assignment_count",
            "completed_class_count",
            "schedule_progress_percent",
            "next_class_topic",
            "material_count",
        )

    @staticmethod
    def _prefetched_list(obj, relation_name):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        if relation_name in cache:
            return list(cache[relation_name])
        return None

    def get_assignment_count(self, obj):
        if hasattr(obj, "assignment_count_value"):
            return obj.assignment_count_value
        return obj.assignments.count()

    def get_completed_class_count(self, obj):
        schedule_items = self._prefetched_list(obj, "schedule_items")
        if schedule_items is not None:
            return sum(1 for item in schedule_items if item.status == ScheduleStatus.COMPLETED)
        return obj.schedule_items.filter(status=ScheduleStatus.COMPLETED).count()

    def get_schedule_progress_percent(self, obj):
        schedule_items = self._prefetched_list(obj, "schedule_items")
        if schedule_items is not None:
            total = len(schedule_items)
            if total == 0:
                return 0
            completed = sum(1 for item in schedule_items if item.status == ScheduleStatus.COMPLETED)
            return round((completed / total) * 100)

        total = obj.schedule_items.count()
        if total == 0:
            return 0
        completed = obj.schedule_items.filter(status=ScheduleStatus.COMPLETED).count()
        return round((completed / total) * 100)

    def get_next_class_topic(self, obj):
        schedule_items = self._prefetched_list(obj, "schedule_items")
        if schedule_items is not None:
            remaining = sorted(
                (item for item in schedule_items if item.status != ScheduleStatus.COMPLETED),
                key=lambda item: (item.class_number, item.order_index),
            )
            return remaining[0].topic if remaining else None
        next_item = obj.schedule_items.exclude(status=ScheduleStatus.COMPLETED).order_by("class_number").first()
        return next_item.topic if next_item else None

    def get_material_count(self, obj):
        materials = self._prefetched_list(obj, "materials")
        if materials is not None:
            return len(materials)
        return obj.materials.count()


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    invite_code = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Enrollment
        fields = ("id", "student", "student_name", "course", "invite_code", "enrolled_at")
        read_only_fields = ("enrolled_at", "student", "course")

    def validate(self, attrs):
        course = attrs.get("course")
        invite_code = str(attrs.get("invite_code", "")).strip().upper()
        if course is None and not invite_code:
            raise serializers.ValidationError("Provide either course or invite_code.")
        if course is not None and invite_code and course.invite_code != invite_code:
            raise serializers.ValidationError("Invite code does not match selected course.")
        if course is None and invite_code:
            resolved = Course.objects.filter(invite_code=invite_code).first()
            if not resolved:
                raise serializers.ValidationError("Invalid invite code.")
            attrs["course"] = resolved
        return attrs

    def create(self, validated_data):
        validated_data.pop("invite_code", None)
        return super().create(validated_data)


class StudentNotebookSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentNotebook
        fields = ("id", "course", "student", "title", "content_text", "created_at", "updated_at")
        read_only_fields = ("student", "created_at", "updated_at")


class StudentFlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentFlashcard
        fields = (
            "id",
            "course",
            "student",
            "question",
            "answer",
            "ease_factor",
            "interval_days",
            "repetitions",
            "due_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "student",
            "ease_factor",
            "interval_days",
            "repetitions",
            "due_at",
            "created_at",
            "updated_at",
        )


class SyllabusUploadSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    syllabus_pdf = serializers.FileField(required=False)
    syllabus_text = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        syllabus_pdf = attrs.get("syllabus_pdf")
        syllabus_text = attrs.get("syllabus_text")

        if syllabus_pdf and syllabus_text:
            raise serializers.ValidationError("Provide either syllabus_pdf or syllabus_text, not both.")

        if not syllabus_pdf and not syllabus_text:
            raise serializers.ValidationError("Provide either syllabus_pdf or syllabus_text.")

        if syllabus_text and len(syllabus_text.strip()) < 40:
            raise serializers.ValidationError("Provide a bit more text so the material can be analyzed properly.")
        return attrs
