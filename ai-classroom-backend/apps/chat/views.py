from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import answer_course_question
from apps.courses.models import Course

from .models import ChatMessage, ChatRole
from .serializers import ChatMessageSerializer


class ChatHistoryView(generics.ListAPIView):
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        return ChatMessage.objects.filter(course_id=self.kwargs["course_id"], student=self.request.user)


class ChatAskView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, course_id):
        course = Course.objects.get(id=course_id)
        question = request.data.get("message", "")
        result = answer_course_question(course=course, question=question)
        
        student = request.user if request.user.is_authenticated else None
        
        message = ChatMessage.objects.create(
            course=course,
            student=student,
            role=ChatRole.STUDENT,
            message=question,
            ai_response=result["answer"],
            sources=result["sources"],
        )
        return Response(ChatMessageSerializer(message).data)
