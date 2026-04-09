import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import client from "../api/client";
import { useChat } from "../hooks/useChat";

const VOICE_LANGUAGE_OPTIONS = [
  { key: "auto", label: "Auto", source: "auto", target: "auto" },
  { key: "eng", label: "ENG", source: "en-IN", target: "en-IN" },
  { key: "hi", label: "HI", source: "hi-IN", target: "hi-IN" },
  { key: "kan", label: "KAN", source: "kn-IN", target: "kn-IN" },
  { key: "tam", label: "TAM", source: "ta-IN", target: "ta-IN" },
  { key: "tel", label: "TEL", source: "te-IN", target: "te-IN" },
];

function evidenceSnippets(sources) {
  return (sources || [])
    .filter((item) => (item?.type === "references" || item?.type === "citation") && item?.snippet)
    .slice(0, 2);
}

export default function ChatInterface({ courseId }) {
  const { messages, loading, error, askQuestion, setMessages } = useChat(courseId);
  const [input, setInput] = useState("");
  const [voiceLanguageKey, setVoiceLanguageKey] = useState("auto");
  const [isRecording, setIsRecording] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const scrollRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const micStreamRef = useRef(null);

  const pickRecordingMimeType = () => {
    if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
      return "";
    }
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
      "",
    ];
    for (const candidate of candidates) {
      if (!candidate || MediaRecorder.isTypeSupported(candidate)) {
        return candidate;
      }
    }
    return "";
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    const saved = localStorage.getItem(`chat_history_${courseId}`);
    if (saved) {
      try {
        setMessages(JSON.parse(saved));
      } catch (_e) {
        setMessages([]);
      }
    } else {
      setMessages([]);
    }
    setInput("");
  }, [courseId]);

  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(`chat_history_${courseId}`, JSON.stringify(messages));
    } else {
      localStorage.removeItem(`chat_history_${courseId}`);
    }
  }, [messages, courseId]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const currentInput = input;
    setInput("");

    await askQuestion(currentInput);
  };

  const clearChat = () => {
    if (window.confirm("Are you sure you want to clear the chat history?")) {
      setMessages([]);
    }
  };

  const startVoiceRecording = async () => {
    try {
      const selectedLanguage = VOICE_LANGUAGE_OPTIONS.find((item) => item.key === voiceLanguageKey) || VOICE_LANGUAGE_OPTIONS[0];

      if (!navigator?.mediaDevices?.getUserMedia) {
        setVoiceStatus("This browser does not support microphone access.");
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;

      if (typeof MediaRecorder === "undefined") {
        setVoiceStatus("This browser does not support audio recording.");
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      const mimeType = pickRecordingMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (evt) => {
        if (evt.data && evt.data.size > 0) {
          audioChunksRef.current.push(evt.data);
        }
      };

      recorder.onstop = async () => {
        try {
          setVoiceStatus("Transcribing with Sarvam, translating, and generating answer...");
          const blob = new Blob(audioChunksRef.current, { type: mimeType || "audio/webm" });
          const ext = (mimeType || "audio/webm").includes("ogg") ? "ogg" : (mimeType || "audio/webm").includes("wav") ? "wav" : "webm";
          const formData = new FormData();
          formData.append("audio", blob, `voice.${ext}`);
          formData.append("audio_mime_type", mimeType || "audio/webm");
          formData.append("source_language_code", selectedLanguage.source);
          formData.append("target_language_code", selectedLanguage.target);

          const voiceRes = await client.post(`/courses/${courseId}/chat/voice-ask/`, formData, {
            headers: { "Content-Type": "multipart/form-data" },
          });
          const data = voiceRes.data || {};
          const userId = Date.now();

          setMessages((prev) => [
            ...prev,
            { role: "STUDENT", message: data.transcript || "[Voice]", id: userId },
            { role: "AI", message: data.answer || "", id: userId + 1, sources: data.sources || [] },
          ]);

          if (data.audio_base64) {
            const mime = data.audio_mime_type || "audio/mpeg";
            const audio = new Audio(`data:${mime};base64,${data.audio_base64}`);
            audio.play().catch(() => undefined);
          }

          const detectedLabel = data?.detected_language_code || selectedLanguage.source;
          setVoiceStatus(`Voice response ready (${detectedLabel}).`);
        } catch (err) {
          const detail = err?.response?.data?.detail || "Could not process voice audio right now.";
          setVoiceStatus(detail);
        }
      };

      recorder.start();
      setIsRecording(true);
      setVoiceStatus("Recording... click again to stop.");
    } catch (_e) {
      setVoiceStatus("Microphone permission denied.");
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }
    setIsRecording(false);
  };

  useEffect(() => {
    return () => {
      if (micStreamRef.current) micStreamRef.current.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return (
    <div className="chat-container panel">
      <div className="chat-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="status-indicator"></div>
          <h3>AI Teacher</h3>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="voice-language-picker" role="group" aria-label="Voice language">
            {VOICE_LANGUAGE_OPTIONS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`voice-lang-btn ${voiceLanguageKey === item.key ? "active" : ""}`}
                onClick={() => setVoiceLanguageKey(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {messages.length > 0 && (
            <button className="btn-clear" onClick={clearChat} title="Clear Chat">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </button>
          )}
          <button
            className="btn-secondary"
            onClick={() => (isRecording ? stopVoiceRecording() : startVoiceRecording())}
            title="Live Voice Chat"
            style={{ padding: "0.35rem 0.6rem" }}
          >
            {isRecording ? "Stop Mic" : "Voice"}
          </button>
        </div>
      </div>
      {voiceStatus && <p className="text-muted" style={{ marginBottom: "0.5rem" }}>{voiceStatus}</p>}
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Hi! I'm your AI Teacher. Upload a syllabus and ask me anything!</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble ${msg.role === "STUDENT" ? "user" : "ai"}`}>
            <div className="bubble-content markdown-body">
              {msg.role === "AI" ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.message}</ReactMarkdown>
              ) : (
                msg.message
              )}
            </div>

            {msg.role === "AI" && evidenceSnippets(msg.sources).length > 0 && (
              <div className="bubble-evidence">
                <strong>PDF Evidence</strong>
                {evidenceSnippets(msg.sources).map((source, index) => (
                  <blockquote key={`${msg.id}-evidence-${index}`}>{source.snippet}</blockquote>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-bubble ai typing">
            <div className="typing-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>
      {error && <p className="text-muted" style={{ marginBottom: "0.5rem" }}>{error}</p>}
      <form className="chat-input" onSubmit={handleSend}>
        <input
          type="text"
          placeholder="Ask a question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          autoComplete="off"
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
