from rest_framework import serializers

from .models import ClassSchedule, Course, CourseMaterial, Enrollment, ScheduleStatus


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


class CourseSerializer(serializers.ModelSerializer):
    schedule_items = ClassScheduleSerializer(many=True, read_only=True)
    materials = CourseMaterialSerializer(many=True, read_only=True)
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)
    assignment_count = serializers.SerializerMethodField()
    completed_class_count = serializers.SerializerMethodField()

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
            "num_assignments",
            "assignment_weightage",
            "extracted_topics",
            "extracted_policies",
            "parse_metadata",
            "schedule_approved_at",
            "created_at",
            "assignment_count",
            "completed_class_count",
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
            "created_at",
            "assignment_count",
            "completed_class_count",
        )

    def get_assignment_count(self, obj):
        return obj.assignments.count()

    def get_completed_class_count(self, obj):
        return obj.schedule_items.filter(status=ScheduleStatus.COMPLETED).count()


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = ("id", "student", "student_name", "course", "enrolled_at")
        read_only_fields = ("enrolled_at",)


class SyllabusUploadSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    syllabus_pdf = serializers.FileField(required=False)
    syllabus_text = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        if not attrs.get("syllabus_pdf") and not attrs.get("syllabus_text"):
            raise serializers.ValidationError("Provide either syllabus_pdf or syllabus_text.")
        return attrs
