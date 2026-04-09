from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from apps.ai_service.language_service import (
    detect_language_from_text,
    normalize_language_code,
    translate_text_with_sarvam_meta,
)
from apps.ai_service.pdf_chat_service import answer_pdf_chat_question

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


class VoiceChatError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class SpeechTranscript:
    transcript: str
    language_code: str


@dataclass
class SpeechAudio:
    audio_base64: str
    mime_type: str


class SpeechService:
    def __init__(self) -> None:
        self._api_key = (getattr(settings, "SARVAM_API_KEY", "") or "").strip()

    @staticmethod
    def _normalize_audio_mime(raw_mime: str | None) -> str:
        mime = (raw_mime or "").strip().lower()
        if not mime:
            return "audio/webm"
        # Strip codec metadata (audio/webm;codecs=opus -> audio/webm)
        mime = mime.split(";", 1)[0].strip()
        if "/" not in mime:
            return "audio/webm"
        return mime

    @staticmethod
    def _mime_to_ext(mime_type: str) -> str:
        if "wav" in mime_type:
            return "wav"
        if "ogg" in mime_type:
            return "ogg"
        if "mp3" in mime_type or "mpeg" in mime_type:
            return "mp3"
        return "webm"

    @staticmethod
    def _codec_to_mime(output_audio_codec: str) -> str:
        codec = (output_audio_codec or "").strip().lower()
        if codec == "wav":
            return "audio/wav"
        if codec in {"mp3", "mpeg"}:
            return "audio/mpeg"
        if codec == "ogg":
            return "audio/ogg"
        return "audio/wav"

    @staticmethod
    def _extract_audio_base64(data: dict[str, Any]) -> str:
        audio_base64 = data.get("audio_base64") or data.get("audio")
        if isinstance(audio_base64, str) and audio_base64.strip():
            return audio_base64.strip()

        audios = data.get("audios")
        if isinstance(audios, list) and audios:
            first = audios[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                nested_audio = first.get("audio_base64") or first.get("audio")
                if isinstance(nested_audio, str) and nested_audio.strip():
                    return nested_audio.strip()

        return ""

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise VoiceChatError("SARVAM_API_KEY is not configured on the server.", status_code=503)

    def transcribe_with_sarvam(
        self,
        *,
        file_obj: Any,
        model: str,
        mode: str = "",
        language_code: str = "unknown",
    ) -> SpeechTranscript:
        self._require_api_key()

        audio_bytes = file_obj.read()
        if not audio_bytes:
            raise VoiceChatError("Uploaded audio file is empty.", status_code=400)
        # Rewind for any later re-use by callers.
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        safe_mime = self._normalize_audio_mime(getattr(file_obj, "content_type", "audio/webm"))
        ext = self._mime_to_ext(safe_mime)
        file_name = getattr(file_obj, "name", f"voice.{ext}") or f"voice.{ext}"

        data: dict[str, str] = {
            "model": (model or "").strip(),
            "language_code": normalize_language_code(language_code, fallback="unknown"),
        }
        if mode is not None:
            data["mode"] = (mode or "").strip()

        headers = {
            "api-subscription-key": self._api_key,
        }
        files = {
            "file": (file_name, audio_bytes, safe_mime),
        }

        try:
            response = requests.post(
                SARVAM_STT_URL,
                headers=headers,
                files=files,
                data=data,
                timeout=75,
            )
            response.raise_for_status()
            payload = response.json() or {}
        except requests.HTTPError as exc:
            message = ""
            try:
                message = (exc.response.json() or {}).get("detail") or (exc.response.text or "")
            except Exception:
                message = str(exc)
            raise VoiceChatError(f"Sarvam STT API error: {message or 'request failed'}", status_code=502) from exc
        except Exception as exc:
            raise VoiceChatError(f"Sarvam STT request failed: {exc}", status_code=502) from exc

        transcript = (
            payload.get("transcript")
            or payload.get("translated_text")
            or payload.get("text")
            or payload.get("result")
            or ""
        )
        detected_language = (
            payload.get("language_code")
            or payload.get("detected_language_code")
            or data["language_code"]
            or "unknown"
        )
        transcript = re.sub(r"\s+", " ", str(transcript)).strip()
        if not transcript:
            raise VoiceChatError("Sarvam STT returned no transcript.", status_code=400)

        return SpeechTranscript(transcript=transcript, language_code=str(detected_language or "unknown"))

    def text_to_speech_with_sarvam(
        self,
        *,
        text: str,
        target_language_code: str,
        speaker: str,
        model: str,
        output_audio_codec: str,
    ) -> SpeechAudio:
        self._require_api_key()
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        if not normalized:
            raise VoiceChatError("Cannot synthesize empty text.", status_code=400)

        codec = (output_audio_codec or "wav").strip().lower()
        payload = {
            "text": normalized,
            "target_language_code": normalize_language_code(target_language_code, fallback="en-IN"),
            "speaker": (speaker or "shubh").strip() or "shubh",
            "model": (model or "bulbul:v3").strip() or "bulbul:v3",
            "output_audio_codec": codec,
        }
        headers = {
            "api-subscription-key": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=75)
            response.raise_for_status()
            data = response.json() or {}
        except requests.HTTPError as exc:
            message = ""
            try:
                message = (exc.response.json() or {}).get("detail") or (exc.response.text or "")
            except Exception:
                message = str(exc)
            raise VoiceChatError(f"Sarvam TTS API error: {message or 'request failed'}", status_code=502) from exc
        except Exception as exc:
            raise VoiceChatError(f"Sarvam TTS request failed: {exc}", status_code=502) from exc

        audio_base64 = self._extract_audio_base64(data)

        if not audio_base64 and data.get("audio_url"):
            try:
                audio_response = requests.get(data["audio_url"], timeout=75)
                audio_response.raise_for_status()
                audio_base64 = base64.b64encode(audio_response.content).decode("utf-8")
            except Exception as exc:
                raise VoiceChatError(f"Sarvam TTS audio fetch failed: {exc}", status_code=502) from exc

        if not audio_base64:
            raise VoiceChatError("Sarvam TTS returned no audio payload.", status_code=502)

        return SpeechAudio(audio_base64=audio_base64, mime_type=self._codec_to_mime(codec))


class VoiceChatService:
    def __init__(self) -> None:
        self.speech = SpeechService()

    @staticmethod
    def _resolve_answer_language(*, transcript_original: SpeechTranscript, transcript_english: SpeechTranscript) -> str:
        detected = normalize_language_code(transcript_original.language_code, fallback="unknown")
        if detected not in {"unknown", "auto"}:
            return detected

        transcript_hint = detect_language_from_text(transcript_original.transcript, default="unknown")
        transcript_hint = normalize_language_code(transcript_hint, fallback="unknown")
        if transcript_hint not in {"unknown", "auto"}:
            return transcript_hint

        english_hint = normalize_language_code(transcript_english.language_code, fallback="unknown")
        if english_hint not in {"unknown", "auto", "en-IN"}:
            return english_hint

        return "en-IN"

    def answer_voice_question(self, *, course, user, audio_file: Any) -> dict[str, Any]:
        stt_model = getattr(settings, "SARVAM_STT_MODEL", "saarika:v2.5")
        stt_mode = getattr(settings, "SARVAM_STT_MODE", "")
        stt_language = getattr(settings, "SARVAM_STT_LANGUAGE_CODE", "unknown")

        transcript_original = self.speech.transcribe_with_sarvam(
            file_obj=audio_file,
            model=stt_model,
            mode=stt_mode,
            language_code=stt_language,
        )

        transcript_english = self.speech.transcribe_with_sarvam(
            file_obj=audio_file,
            model="saaras:v3",
            mode="translate",
            language_code="unknown",
        )

        qa_result = answer_pdf_chat_question(course=course, question=transcript_english.transcript, user=user, top_k=5)
        english_answer = (qa_result.get("answer_text") or "").strip()
        if not english_answer:
            english_answer = "I could not find a grounded answer in the uploaded class materials."

        preferred_answer_language = self._resolve_answer_language(
            transcript_original=transcript_original,
            transcript_english=transcript_english,
        )

        localized = translate_text_with_sarvam_meta(
            english_answer,
            source_language_code="en-IN",
            target_language_code=preferred_answer_language,
        )
        answer_text = (localized.get("translated_text") or english_answer).strip()
        answer_language_code = preferred_answer_language
        used_translation = bool(localized.get("used_translation"))
        if used_translation:
            translated_target = normalize_language_code(
                localized.get("target_language_code") or preferred_answer_language,
                fallback=preferred_answer_language,
            )
            if translated_target not in {"unknown", "auto"}:
                answer_language_code = translated_target

        tts_speaker = getattr(settings, "SARVAM_TTS_SPEAKER", "shubh")
        tts_model = getattr(settings, "SARVAM_TTS_MODEL", "bulbul:v3")
        tts_codec = getattr(settings, "SARVAM_TTS_OUTPUT_CODEC", "wav")

        try:
            audio = self.speech.text_to_speech_with_sarvam(
                text=answer_text,
                target_language_code=answer_language_code,
                speaker=tts_speaker,
                model=tts_model,
                output_audio_codec=tts_codec,
            )
        except VoiceChatError as first_tts_error:
            logger.warning("TTS failed for %s without language fallback: %s", answer_language_code, first_tts_error.detail)
            raise

        return {
            "transcript_original": transcript_original.transcript,
            "transcript_english": transcript_english.transcript,
            "detected_language_code": normalize_language_code(transcript_original.language_code, fallback="unknown"),
            "answer_text": answer_text,
            "answer_language_code": answer_language_code,
            "answer_audio_base64": audio.audio_base64,
            "answer_audio_mime_type": audio.mime_type,
            "sources": qa_result.get("sources") or [],
        }
