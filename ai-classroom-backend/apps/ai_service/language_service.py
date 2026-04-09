import logging
import base64
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


_LANGUAGE_SCRIPT_HINTS = [
    ("hi-IN", re.compile(r"[\u0900-\u097F]")),
    ("ta-IN", re.compile(r"[\u0B80-\u0BFF]")),
    ("te-IN", re.compile(r"[\u0C00-\u0C7F]")),
    ("kn-IN", re.compile(r"[\u0C80-\u0CFF]")),
    ("ml-IN", re.compile(r"[\u0D00-\u0D7F]")),
    ("bn-IN", re.compile(r"[\u0980-\u09FF]")),
    ("gu-IN", re.compile(r"[\u0A80-\u0AFF]")),
]


def normalize_language_code(language_code: str | None, fallback: str = "en-IN") -> str:
    raw = (language_code or "").strip()
    if not raw:
        return fallback
    lowered = raw.lower()
    if lowered in {"auto", "unknown"}:
        return "unknown"
    return raw


def detect_language_from_text(text: str, default: str = "en-IN") -> str:
    sample = (text or "").strip()
    if not sample:
        return default

    for code, pattern in _LANGUAGE_SCRIPT_HINTS:
        if pattern.search(sample):
            return code
    return default


def translate_text_with_sarvam_meta(
    text: str,
    source_language_code: str = "en-IN",
    target_language_code: str = "en-IN",
) -> dict:
    normalized = (text or "").strip()
    if not normalized:
        return {
            "translated_text": "",
            "source_language_code": normalize_language_code(source_language_code, fallback="en-IN"),
            "target_language_code": normalize_language_code(target_language_code, fallback="en-IN"),
            "used_translation": False,
        }

    normalized_source = normalize_language_code(source_language_code, fallback="en-IN")
    normalized_target = normalize_language_code(target_language_code, fallback="en-IN")

    if normalized_source == "unknown":
        normalized_source = detect_language_from_text(normalized, default="en-IN")
    if normalized_target == "unknown":
        normalized_target = normalized_source

    if normalized_source == normalized_target:
        return {
            "translated_text": normalized,
            "source_language_code": normalized_source,
            "target_language_code": normalized_target,
            "used_translation": False,
        }

    api_key = getattr(settings, "SARVAM_API_KEY", "")
    if not api_key:
        return {
            "translated_text": normalized,
            "source_language_code": normalized_source,
            "target_language_code": normalized_target,
            "used_translation": False,
        }

    payload = {
        "input": [normalized],
        "source_language_code": normalized_source,
        "target_language_code": normalized_target,
        "speaker_gender": "Female",
        "mode": "formal",
        "model": "mayura:v1",
        "enable_preprocessing": True,
    }
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post("https://api.sarvam.ai/translate", json=payload, headers=headers, timeout=45)
        response.raise_for_status()
        data = response.json() or {}
        translated = (data.get("translated_text") or [normalized])[0] or normalized
        detected_source = data.get("source_language_code") or normalized_source
        return {
            "translated_text": translated,
            "source_language_code": detected_source,
            "target_language_code": normalized_target,
            "used_translation": True,
        }
    except Exception as exc:
        logger.warning("Sarvam translation failed (%s -> %s): %s", normalized_source, normalized_target, exc)
        return {
            "translated_text": normalized,
            "source_language_code": normalized_source,
            "target_language_code": normalized_target,
            "used_translation": False,
        }


def translate_text_with_sarvam(text: str, source_language_code: str = "en-IN", target_language_code: str = "en-IN") -> str:
    """Translate text via Sarvam when configured; otherwise return input text unchanged."""
    return translate_text_with_sarvam_meta(
        text,
        source_language_code=source_language_code,
        target_language_code=target_language_code,
    ).get("translated_text", (text or "").strip())


def transcribe_audio_with_sarvam(
    audio_bytes: bytes,
    source_language_code: str = "unknown",
    mime_type: str = "audio/webm",
) -> dict:
    """Transcribe audio bytes via Sarvam STT endpoint with model fallback."""
    api_key = getattr(settings, "SARVAM_API_KEY", "")
    if not api_key or not audio_bytes:
        return {
            "transcript": "",
            "language_code": source_language_code or "unknown",
            "error": "SARVAM_API_KEY missing or empty audio payload.",
        }

    headers = {
        "api-subscription-key": api_key,
    }

    safe_mime = (mime_type or "audio/webm").lower()
    if "ogg" in safe_mime:
        suffix = ".ogg"
        upload_content_type = "audio/ogg"
    elif "wav" in safe_mime:
        suffix = ".wav"
        upload_content_type = "audio/wav"
    else:
        suffix = ".webm"
        upload_content_type = "audio/webm"

    try:
        language_candidates = []
        normalized_lang = (source_language_code or "unknown").strip() or "unknown"
        if normalized_lang.lower() in {"auto", "unknown"}:
            language_candidates = ["unknown", "en-IN"]
        else:
            language_candidates = [normalized_lang, "unknown"]

        model_candidates = ["saaras:v3", "saaras:v2"]
        last_error = ""

        for model in model_candidates:
            for lang_code in language_candidates:
                try:
                    files = {"file": (f"voice{suffix}", audio_bytes, upload_content_type)}
                    data = {"language_code": lang_code, "model": model}
                    response = requests.post(
                        "https://api.sarvam.ai/speech-to-text",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=60,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    transcript = (
                        payload.get("transcript")
                        or payload.get("text")
                        or payload.get("result")
                        or ""
                    )
                    detected_lang = (
                        payload.get("language_code")
                        or payload.get("detected_language_code")
                        or lang_code
                    )
                    if transcript:
                        return {
                            "transcript": transcript,
                            "language_code": detected_lang,
                            "error": "",
                        }
                except Exception as model_exc:
                    last_error = str(model_exc)

        return {
            "transcript": "",
            "language_code": normalized_lang,
            "error": last_error or "No transcript returned by Sarvam STT.",
        }
    except Exception as exc:
        logger.warning("Sarvam speech-to-text failed: %s", exc)
        return {
            "transcript": "",
            "language_code": source_language_code or "unknown",
            "error": str(exc),
        }


def synthesize_speech_with_sarvam(text: str, target_language_code: str = "en-IN") -> str | None:
    """Convert text to audio via Sarvam TTS endpoint and return base64-encoded audio."""
    normalized = (text or "").strip()
    api_key = getattr(settings, "SARVAM_API_KEY", "")
    if not api_key or not normalized:
        return None

    payload = {
        "text": normalized,
        "target_language_code": target_language_code,
        "speaker": "anushka",
        "model": "bulbul:v1",
    }
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post("https://api.sarvam.ai/text-to-speech", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        if data.get("audio_base64"):
            return data["audio_base64"]

        audio_url = data.get("audio_url")
        if audio_url:
            audio_res = requests.get(audio_url, timeout=60)
            audio_res.raise_for_status()
            return base64.b64encode(audio_res.content).decode("utf-8")
    except Exception as exc:
        logger.warning("Sarvam text-to-speech failed: %s", exc)

    return None
