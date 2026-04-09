import client from "./client";

export async function askPdfChatQuestion({ classroomId, question }) {
  const response = await client.post(`/courses/${classroomId}/chat/ask/`, {
    classroom_id: classroomId,
    question,
  });

  const payload = response?.data || {};
  return {
    classroomId: payload.classroom_id,
    question: payload.question,
    answerText: payload.answer_text,
    sources: payload.sources || [],
    messageId: payload.message_id,
    timestamp: payload.timestamp,
  };
}

export async function askClassroomVoiceQuestion(classroomId, audioBlob, mimeType = "audio/webm") {
  const safeMime = (mimeType || "audio/webm").split(";")[0] || "audio/webm";
  const extension = safeMime.includes("ogg") ? "ogg" : safeMime.includes("wav") ? "wav" : "webm";
  const formData = new FormData();
  formData.append("audio", audioBlob, `voice.${extension}`);

  const response = await client.post(`/v1/classrooms/${classroomId}/chat/voice/`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  const payload = response?.data || {};
  return {
    transcriptOriginal: payload.transcript_original || "",
    transcriptEnglish: payload.transcript_english || "",
    detectedLanguageCode: payload.detected_language_code || "unknown",
    answerText: payload.answer_text || "",
    answerLanguageCode: payload.answer_language_code || "en-IN",
    answerAudioBase64: payload.answer_audio_base64 || "",
    answerAudioMimeType: payload.answer_audio_mime_type || "audio/wav",
    assistantMessage: payload.assistant_message || null,
  };
}
