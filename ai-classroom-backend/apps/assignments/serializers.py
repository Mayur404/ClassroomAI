from rest_framework import serializers

from .models import Assignment


class AssignmentSerializer(serializers.ModelSerializer):
    grade = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "course",
            "title",
            "description",
            "type",
            "status",
            "total_marks",
            "questions",
            "rubric",
            "answer_key",
            "due_date",
            "covered_until_class",
            "created_at",
            "published_at",
            "grade",
        )
        read_only_fields = ("status", "created_at", "published_at", "grade")

    def get_grade(self, obj):
        request = self.context.get("request")
        if not request or request.user.role != "STUDENT":
            return None
        submission = obj.submissions.filter(student=request.user).order_by("-submitted_at").first()
        if not submission:
            return None
        return {"score": submission.ai_grade, "out_of": obj.total_marks}


class AssignmentGenerateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    type = serializers.ChoiceField(choices=("MCQ", "ESSAY", "CODING"))
    due_date = serializers.DateTimeField()
