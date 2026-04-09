import { useCallback, useState } from "react";

import { askPdfChatQuestion } from "../api/chat.service";

export function useChat(classroomId) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const askQuestion = useCallback(
    async (question) => {
      const trimmedQuestion = (question || "").trim();
      if (!trimmedQuestion || !classroomId) {
        return;
      }

      const userMessage = {
        id: `user-${Date.now()}`,
        role: "STUDENT",
        message: trimmedQuestion,
        timestamp: new Date().toISOString(),
      };

      setMessages((previous) => [...previous, userMessage]);
      setLoading(true);
      setError("");

      try {
        const result = await askPdfChatQuestion({ classroomId, question: trimmedQuestion });
        const assistantMessage = {
          id: result.messageId || `assistant-${Date.now()}`,
          role: "AI",
          message: result.answerText || "",
          sources: result.sources || [],
          timestamp: result.timestamp || new Date().toISOString(),
        };
        setMessages((previous) => [...previous, assistantMessage]);
      } catch (requestError) {
        const detail = requestError?.response?.data?.detail;
        setError(detail || "Unable to reach the AI tutor right now.");
      } finally {
        setLoading(false);
      }
    },
    [classroomId]
  );

  return { messages, loading, error, askQuestion, setMessages };
}
