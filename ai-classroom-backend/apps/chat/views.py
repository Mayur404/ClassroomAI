from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import StreamingHttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import answer_course_question
from apps.ai_service.streaming_service import stream_response_to_sse
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
        course = get_object_or_404(Course, id=course_id)
        question = str(request.data.get("message", "")).strip()
        if not question:
            return Response({"detail": "Message cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        result = answer_course_question(course=course, question=question, user=request.user, include_context=True)

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=question,
            ai_response=result["answer"],
            sources=result["sources"],
        )
        return Response(ChatMessageSerializer(message).data)


class ChatFeedbackView(APIView):
    """Submit feedback on chat answer quality for improvement tracking."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, message_id):
        message = get_object_or_404(ChatMessage, id=message_id, student=request.user)
        
        score = request.data.get("score")  # -1 (unhelpful) or 1 (helpful)
        if score not in [-1, 1]:
            return Response({"detail": "Score must be -1 or 1"}, status=status.HTTP_400_BAD_REQUEST)
        
        feedback_text = str(request.data.get("text", "")).strip()[:500]
        
        message.feedback_score = score
        message.feedback_text = feedback_text
        message.feedback_timestamp = timezone.now()
        message.save(update_fields=["feedback_score", "feedback_text", "feedback_timestamp"])
        
        return Response({
            "status": "recorded",
            "message_id": message.id,
            "feedback_score": message.feedback_score,
        })


class ChatStreamingView(APIView):
    """Stream response tokens in real-time using Server-Sent Events (SSE)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id)
        question = str(request.data.get("message", "")).strip()
        
        if not question:
            return Response(
                {"detail": "Message cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create student message immediately
        student_message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=question,
            ai_response="[Streaming...]",
        )
        
        # Stream response
        response = StreamingHttpResponse(
            stream_response_to_sse(
                course_id=course_id,
                question=question,
                user=request.user,
                include_context=True,
                message_id=student_message.id
            ),
            content_type='text/event-stream'
        )
        
        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        
        return response

