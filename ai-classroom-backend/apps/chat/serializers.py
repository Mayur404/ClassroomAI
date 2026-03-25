from rest_framework import serializers

from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = (
            "id", 
            "course", 
            "student", 
            "role", 
            "message", 
            "ai_response", 
            "sources", 
            "timestamp",
            "feedback_score",
            "feedback_text",
            "feedback_timestamp",
        )
        read_only_fields = ("student", "role", "ai_response", "sources", "timestamp", "feedback_timestamp")
