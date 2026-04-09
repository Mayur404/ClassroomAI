import base64
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from apps.ai_service.language_service import (
    synthesize_speech_with_sarvam,
    transcribe_audio_with_sarvam,
    translate_text_with_sarvam,
)
from apps.ai_service.services import answer_course_question
from apps.courses.models import Course
from .models import ChatMessage, ChatRole


class VoiceChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.course_id = int(self.scope["url_route"]["kwargs"]["course_id"])
        has_access = await self._has_course_access(user.id, self.course_id, user.role)
        if not has_access:
            await self.close(code=4403)
            return

        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected", "course_id": self.course_id}))

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"type": "error", "message": "Invalid payload"}))
            return

        action = payload.get("action")
        if action == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

        if action != "voice_query":
            await self.send(text_data=json.dumps({"type": "error", "message": "Unsupported action"}))
            return

        source_language_code = str(payload.get("source_language_code", "en-IN") or "en-IN")
        target_language_code = str(payload.get("target_language_code", source_language_code) or source_language_code)
        audio_mime_type = str(payload.get("audio_mime_type", "audio/webm") or "audio/webm")
        transcript = str(payload.get("transcript", "")).strip()
        audio_b64 = payload.get("audio_base64")

        if not transcript and not audio_b64:
            await self.send(text_data=json.dumps({"type": "error", "message": "No audio or transcript provided"}))
            return

        if not transcript and audio_b64:
            try:
                audio_bytes = base64.b64decode(audio_b64)
                transcript = await sync_to_async(transcribe_audio_with_sarvam)(
                    audio_bytes,
                    source_language_code,
                    audio_mime_type,
                )
            except Exception:
                transcript = ""

        if not transcript:
            await self.send(text_data=json.dumps({"type": "error", "message": "Could not transcribe audio"}))
            return

        english_question = await sync_to_async(translate_text_with_sarvam)(
            transcript,
            source_language_code=source_language_code,
            target_language_code="en-IN",
        )

        result = await self._answer_question(english_question)
        localized_answer = await sync_to_async(translate_text_with_sarvam)(
            result["answer"],
            source_language_code="en-IN",
            target_language_code=target_language_code,
        )

        audio_answer_b64 = await sync_to_async(synthesize_speech_with_sarvam)(localized_answer, target_language_code)

        await self._persist_chat(transcript, localized_answer, result.get("sources", []))

        await self.send(
            text_data=json.dumps(
                {
                    "type": "assistant_response",
                    "transcript": transcript,
                    "answer": localized_answer,
                    "sources": result.get("sources", []),
                    "audio_base64": audio_answer_b64,
                }
            )
        )

    @sync_to_async
    def _has_course_access(self, user_id, course_id, role):
        if role == "TEACHER":
            return Course.objects.filter(id=course_id, teacher_id=user_id).exists()
        return Course.objects.filter(id=course_id, enrollments__student_id=user_id).exists()

    @sync_to_async
    def _answer_question(self, question):
        user = self.scope["user"]
        if user.role == "TEACHER":
            course = Course.objects.get(id=self.course_id, teacher=user)
        else:
            course = Course.objects.get(id=self.course_id, enrollments__student=user)
        return answer_course_question(course=course, question=question, user=user, include_context=True)

    @sync_to_async
    def _persist_chat(self, question, answer, sources):
        ChatMessage.objects.create(
            course_id=self.course_id,
            student=self.scope["user"],
            role=ChatRole.STUDENT,
            message=question,
            ai_response=answer,
            sources=sources,
        )
