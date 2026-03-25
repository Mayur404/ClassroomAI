from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import answer_course_question
from apps.courses.models import Course

from .models import ChatMessage, ChatRole
from .serializers import ChatMessageSerializer


class ChatHistoryView(generics.ListAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatMessage.objects.filter(course_id=self.kwargs["course_id"], student=self.request.user)


class ChatAskView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        question = str(request.data.get("message", "")).strip()
        if not question:
            return Response({"detail": "Message cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        result = answer_course_question(course=course, question=question)

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=question,
            ai_response=result["answer"],
            sources=result["sources"],
        )
        return Response(ChatMessageSerializer(message).data)
