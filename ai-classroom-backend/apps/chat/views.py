from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import StreamingHttpResponse
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_service.services import answer_course_question
from apps.ai_service.pdf_chat_service import answer_pdf_chat_question
from apps.ai_service.streaming_service import stream_response_to_sse
from apps.ai_service.language_service import (
    normalize_language_code,
    synthesize_speech_with_sarvam,
    transcribe_audio_with_sarvam,
    translate_text_with_sarvam_meta,
    translate_text_with_sarvam,
)
from apps.courses.models import Course

from .models import ChatMessage, ChatRole
from .serializers import ChatMessageSerializer


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
    """Reliable voice ask endpoint (record -> upload -> STT -> RAG answer -> optional TTS)."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, course_id):
        if request.user.role not in {"STUDENT", "TEACHER"}:
            raise PermissionDenied("Voice AI tutor is available only for students and teachers.")

        course = _resolve_accessible_course(request.user, course_id)
        source_language_code = str(request.data.get("source_language_code", "unknown")).strip() or "unknown"
        target_language_code = str(request.data.get("target_language_code", "auto")).strip() or "auto"
        source_language_code = normalize_language_code(source_language_code, fallback="unknown")
        target_language_code = normalize_language_code(target_language_code, fallback="unknown")

        transcript = str(request.data.get("transcript", "")).strip()
        audio_file = request.FILES.get("audio")

        if not transcript and not audio_file:
            return Response({"detail": "Provide transcript or audio."}, status=status.HTTP_400_BAD_REQUEST)

        if not transcript and not getattr(settings, "SARVAM_API_KEY", ""):
            return Response(
                {"detail": "Voice pipeline unavailable: SARVAM_API_KEY is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        detected_language_code = source_language_code
        if not transcript and audio_file:
            audio_bytes = audio_file.read()
            mime_hint = str(request.data.get("audio_mime_type", "")).strip() or getattr(audio_file, "content_type", "audio/webm") or "audio/webm"
            stt_result = transcribe_audio_with_sarvam(
                audio_bytes=audio_bytes,
                source_language_code=source_language_code,
                mime_type=mime_hint,
            )
            transcript = (stt_result.get("transcript") or "").strip()
            detected_language_code = stt_result.get("language_code") or detected_language_code
            stt_error = stt_result.get("error")
        else:
            stt_error = ""

        if not transcript:
            return Response(
                {"detail": f"Could not transcribe audio. {stt_error}".strip()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        effective_source_language = detected_language_code or source_language_code or "en-IN"
        effective_target_language = target_language_code
        if effective_target_language == "unknown":
            effective_target_language = effective_source_language if effective_source_language not in {"unknown", "auto"} else "en-IN"

        normalized_question = translate_text_with_sarvam(
            transcript,
            source_language_code=effective_source_language,
            target_language_code="en-IN",
        )

        result = answer_course_question(course=course, question=normalized_question, user=request.user, include_context=True)
        localized_answer = translate_text_with_sarvam(
            result["answer"],
            source_language_code="en-IN",
            target_language_code=effective_target_language,
        )
        audio_base64 = synthesize_speech_with_sarvam(localized_answer, target_language_code=effective_target_language)

        message = ChatMessage.objects.create(
            course=course,
            student=request.user,
            role=ChatRole.STUDENT,
            message=transcript,
            ai_response=localized_answer,
            sources=result.get("sources", []),
        )

        return Response(
            {
                "id": message.id,
                "transcript": transcript,
                "answer": localized_answer,
                "sources": result.get("sources", []),
                "audio_base64": audio_base64,
                "detected_language_code": effective_source_language,
                "resolved_target_language_code": effective_target_language,
                "audio_mime_type": "audio/mpeg" if audio_base64 else None,
            },
            status=status.HTTP_200_OK,
        )
