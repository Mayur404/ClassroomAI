from rest_framework import serializers

from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    student_email = serializers.EmailField(source="student.email", read_only=True)
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    final_grade = serializers.SerializerMethodField()
    grade_source = serializers.SerializerMethodField()

    def validate_answers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("answers must be an object keyed by question number.")

        normalized = {}
        for key, answer in value.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                raise serializers.ValidationError("Each answer must have a question number key.")

            if isinstance(answer, list):
                text_value = ", ".join(str(item).strip() for item in answer if str(item).strip())
            elif answer is None:
                text_value = ""
            else:
                text_value = str(answer).strip()

            if len(text_value) > 5000:
                raise serializers.ValidationError("Each answer must be 5000 characters or fewer.")

            normalized[normalized_key] = text_value

        return normalized

    def get_final_grade(self, obj):
        return obj.final_grade

    def get_grade_source(self, obj):
        return obj.grade_source

    class Meta:
        model = Submission
        fields = (
            "id",
            "assignment",
            "student",
            "answers",
            "status",
            "submitted_at",
            "ai_grade",
            "ai_feedback",
            "score_breakdown",
            "grading_version",
            "teacher_grade",
            "teacher_feedback",
            "teacher_graded_at",
            "final_grade",
            "grade_source",
            "graded_at",
            "student_name",
            "student_email",
            "assignment_title",
        )
        read_only_fields = (
            "assignment",
            "student",
            "status",
            "submitted_at",
            "ai_grade",
            "ai_feedback",
            "score_breakdown",
            "grading_version",
            "teacher_grade",
            "teacher_feedback",
            "teacher_graded_at",
            "final_grade",
            "grade_source",
            "graded_at",
            "student_name",
            "student_email",
            "assignment_title",
        )


class SubmissionTeacherGradeSerializer(serializers.Serializer):
    teacher_grade = serializers.FloatField(min_value=0)
    teacher_feedback = serializers.CharField(required=False, allow_blank=True, max_length=4000)

    def validate_teacher_grade(self, value):
        submission = self.context["submission"]
        max_marks = float(submission.assignment.total_marks or 0)
        if value > max_marks:
            raise serializers.ValidationError(f"Teacher grade cannot exceed {max_marks:g}.")
        return round(float(value), 2)
