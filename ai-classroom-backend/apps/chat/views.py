import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import StreamingHttpResponse
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ai_service.pdf_chat_service import answer_pdf_chat_question
from apps.ai_service.streaming_service import stream_response_to_sse
from apps.ai_service.voice_chat_service import VoiceChatService, VoiceChatError
from apps.ai_service.language_service import (
    normalize_language_code,
)
from apps.courses.models import Course

from .models import ChatMessage, ChatRole
from .serializers import ChatMessageSerializer

logger = logging.getLogger(__name__)


class ChatHistoryView(generics.ListAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatMessage.objects.filter(course_id=self.kwargs["course_id"], student=self.request.user)


def _resolve_accessible_course(user, course_id):
    if user.role == "TEACHER":
        return get_object_or_404(Course, id=course_id, teacher=user)
    return get_object_or_404(Course, id=course_id, enrollments__student=user)


class ChatAskView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        if request.user.role not in {"TEACHER", "STUDENT"}:
            raise PermissionDenied("Chat access is not available for this user.")

        course = _resolve_accessible_course(request.user, course_id)
        classroom_id = int(request.data.get("classroom_id") or course_id)
        if classroom_id != course.id:
            return Response({"detail": "classroom_id does not match requested course."}, status=status.HTTP_400_BAD_REQUEST)

        question = str(request.data.get("question", request.data.get("message", ""))).strip()
        if not question:
            return Response({"detail": "Question cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = answer_pdf_chat_question(course=course, question=question, user=request.user, top_k=5)
        except Exception as exc:
            return Response(
                {
                    "detail": "AI service is temporarily unavailable.",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        answer_text = result.get("answer_text", "")
        sources = result.get("sources", [])

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=question,
            ai_response=answer_text,
            sources=sources,
        )

        return Response(
            {
                "classroom_id": course.id,
                "question": question,
                "answer_text": answer_text,
                "ai_response": answer_text,
                "sources": sources,
                "message_id": message.id,
                "timestamp": message.timestamp,
                "chat_message": ChatMessageSerializer(message).data,
            },
            status=status.HTTP_200_OK,
        )


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
        if request.user.role not in {"TEACHER", "STUDENT"}:
            raise PermissionDenied("Chat access is not available for this user.")

        course = _resolve_accessible_course(request.user, course_id)
        question = str(request.data.get("message", "")).strip()
        source_language_code = normalize_language_code(request.data.get("source_language_code"), fallback="unknown")
        target_language_code = normalize_language_code(request.data.get("target_language_code"), fallback="unknown")
        
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
                message_id=student_message.id,
                source_language_code=source_language_code,
                target_language_code=target_language_code,
            ),
            content_type='text/event-stream'
        )
        
        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        
        return response


class VoiceAskView(APIView):
    """Backward-compatible voice ask endpoint for existing frontend clients."""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "voice_chat"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, course_id):
        if request.user.role not in {"TEACHER", "STUDENT"}:
            raise PermissionDenied("Voice AI tutor is available only for teachers and students.")

        course = _resolve_accessible_course(request.user, course_id)
        audio_file = request.FILES.get("audio")
        if not audio_file:
            return Response({"detail": "Provide audio file."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = VoiceChatService().answer_voice_question(course=course, user=request.user, audio_file=audio_file)
        except VoiceChatError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)
        except Exception as exc:
            logger.exception("Voice tutor request failed for course %s user %s", course.id, request.user.id)
            return Response(
                {
                    "detail": str(exc) if settings.DEBUG else "Voice processing failed.",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=result["transcript_original"],
            ai_response=result["answer_text"],
            sources=result.get("sources", []),
        )

        return Response(
            {
                "id": message.id,
                "transcript": result["transcript_original"],
                "answer": result["answer_text"],
                "sources": result.get("sources", []),
                "audio_base64": result["answer_audio_base64"],
                "detected_language_code": result["detected_language_code"],
                "resolved_target_language_code": result["answer_language_code"],
                "audio_mime_type": result["answer_audio_mime_type"],
                "assistant_message": ChatMessageSerializer(message).data,
            },
            status=status.HTTP_200_OK,
        )


class ClassroomVoiceChatView(APIView):
    """Classroom voice chat endpoint with auto language detection via Sarvam."""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "voice_chat"
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, classroom_id):
        if request.user.role not in {"TEACHER", "STUDENT"}:
            raise PermissionDenied("Voice classroom chat is available only for teachers and students.")

        course = _resolve_accessible_course(request.user, classroom_id)
        audio_file = request.FILES.get("audio")
        if not audio_file:
            return Response({"detail": "Audio file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = VoiceChatService().answer_voice_question(course=course, user=request.user, audio_file=audio_file)
        except VoiceChatError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)
        except Exception as exc:
            logger.exception("Classroom voice request failed for course %s user %s", course.id, request.user.id)
            return Response(
                {
                    "detail": str(exc) if settings.DEBUG else "Voice processing failed.",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=result["transcript_original"],
            ai_response=result["answer_text"],
            sources=result.get("sources", []),
        )
        serialized = ChatMessageSerializer(message).data

        return Response(
            {
                "transcript_original": result["transcript_original"],
                "transcript_english": result["transcript_english"],
                "detected_language_code": result["detected_language_code"],
                "answer_text": result["answer_text"],
                "answer_language_code": result["answer_language_code"],
                "answer_audio_base64": result["answer_audio_base64"],
                "answer_audio_mime_type": result["answer_audio_mime_type"],
                "assistant_message": serialized,
            },
            status=status.HTTP_200_OK,
        )
