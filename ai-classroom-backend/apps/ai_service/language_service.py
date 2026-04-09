import logging
import base64
import re
from typing import Any

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

_LANGUAGE_CODE_ALIASES = {
    "en": "en-IN",
    "en-in": "en-IN",
    "en_us": "en-IN",
    "en-us": "en-IN",
    "english": "en-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "hindi": "hi-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "tamil": "ta-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "telugu": "te-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
    "kannada": "kn-IN",
    "ml": "ml-IN",
    "ml-in": "ml-IN",
    "malayalam": "ml-IN",
    "bn": "bn-IN",
    "bn-in": "bn-IN",
    "bengali": "bn-IN",
    "gu": "gu-IN",
    "gu-in": "gu-IN",
    "gujarati": "gu-IN",
}

_LANGUAGE_NAMES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
}


def normalize_language_code(language_code: str | None, fallback: str = "en-IN") -> str:
    raw = (language_code or "").strip()
    if not raw:
        return fallback
    lowered = raw.lower()
    if lowered in {"auto", "unknown"}:
        return "unknown"
    return _LANGUAGE_CODE_ALIASES.get(lowered, raw)


def detect_language_from_text(text: str, default: str = "en-IN") -> str:
    sample = (text or "").strip()
    if not sample:
        return default

    for code, pattern in _LANGUAGE_SCRIPT_HINTS:
        if pattern.search(sample):
            return code
    return default


def _translation_chunks(text: str, max_chars: int = 1800) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    pieces = re.split(r"(?<=[.!?])\s+|\n{2,}", normalized)
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        part = (piece or "").strip()
        if not part:
            continue
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(part) > max_chars:
            chunks.append(part[:max_chars].strip())
            part = part[max_chars:].strip()
        if part:
            current = part

    if current:
        chunks.append(current)
    return chunks


def _extract_translated_text(payload: dict[str, Any], default: str) -> str:
    translated = payload.get("translated_text")
    if isinstance(translated, str) and translated.strip():
        return translated.strip()
    if isinstance(translated, list) and translated:
        first = translated[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return default


def _language_name(language_code: str) -> str:
    normalized = normalize_language_code(language_code, fallback=language_code or "English")
    return _LANGUAGE_NAMES.get(normalized, normalized)


def _translate_with_groq(text: str, source_language_code: str, target_language_code: str) -> str:
    try:
        from apps.ai_service.services import call_ollama

        source_name = _language_name(source_language_code)
        target_name = _language_name(target_language_code)
        prompt = (
            f"Translate the following text from {source_name} to {target_name}. "
            "Preserve meaning, citations, filenames, page numbers, bullets, and line breaks. "
            "Return only the translated text.\n\n"
            f"Text:\n{text}"
        )
        translated = (call_ollama(prompt, format_json=False, temperature=0.1) or "").strip()
        return translated or text
    except Exception as exc:
        logger.warning(
            "Groq translation fallback failed (%s -> %s): %s",
            source_language_code,
            target_language_code,
            exc,
        )
        return text


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
        translated = _translate_with_groq(normalized, normalized_source, normalized_target)
        return {
            "translated_text": translated,
            "source_language_code": normalized_source,
            "target_language_code": normalized_target,
            "used_translation": translated != normalized,
        }

    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    translate_model = getattr(settings, "SARVAM_TRANSLATE_MODEL", "sarvam-translate:v1")
    translated_chunks: list[str] = []
    used_translation = False

    for chunk in _translation_chunks(normalized):
        payload = {
            "input": chunk,
            "source_language_code": normalized_source,
            "target_language_code": normalized_target,
            "speaker_gender": "Female",
            "mode": "formal",
            "model": translate_model,
            "enable_preprocessing": False,
        }
        try:
            response = requests.post("https://api.sarvam.ai/translate", json=payload, headers=headers, timeout=45)
            response.raise_for_status()
            data = response.json() or {}
            translated_chunks.append(_extract_translated_text(data, chunk))
            used_translation = True
        except Exception as exc:
            logger.warning("Sarvam translation failed (%s -> %s): %s", normalized_source, normalized_target, exc)
            translated_chunks.append(_translate_with_groq(chunk, normalized_source, normalized_target))
            used_translation = used_translation or (translated_chunks[-1] != chunk)

    translated = "\n\n".join(part for part in translated_chunks if part.strip()).strip() or normalized
    return {
        "translated_text": translated,
        "source_language_code": normalized_source,
        "target_language_code": normalized_target,
        "used_translation": used_translation,
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
