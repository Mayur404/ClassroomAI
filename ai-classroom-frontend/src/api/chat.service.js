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
