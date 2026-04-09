import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askClassroomVoiceQuestion } from "../api/chat.service";
import { useChat } from "../hooks/useChat";

function evidenceSnippets(sources) {
  return (sources || [])
    .filter((item) => (item?.type === "references" || item?.type === "citation") && item?.snippet)
    .slice(0, 2);
}

function formatDuration(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const mins = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function VoiceResponseCard({ dataUrl }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    const onLoaded = () => setDuration(audio.duration || 0);
    const onTimeUpdate = () => setCurrentTime(audio.currentTime || 0);
    const onEnded = () => setIsPlaying(false);

    audio.addEventListener("loadedmetadata", onLoaded);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("loadedmetadata", onLoaded);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
    };
  }, []);

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch (_error) {
      setIsPlaying(false);
    }
  };

  const seekAudio = (event) => {
    const audio = audioRef.current;
    if (!audio) return;
    const nextValue = Number(event.target.value);
    audio.currentTime = Number.isFinite(nextValue) ? nextValue : 0;
    setCurrentTime(audio.currentTime || 0);
  };

  return (
    <div className="voice-response-card">
      <audio ref={audioRef} src={dataUrl} preload="metadata" />
      <div className="voice-response-row">
        <strong>Voice response</strong>
        <button type="button" className="btn-secondary" onClick={togglePlayback}>
          {isPlaying ? "Pause" : "Play"}
        </button>
      </div>
      <input
        type="range"
        min="0"
        max={duration || 0}
        step="0.01"
        value={Math.min(currentTime, duration || 0)}
        onChange={seekAudio}
      />
      <div className="voice-response-meta">
        <span>{formatDuration(currentTime)}</span>
        <span>{formatDuration(duration)}</span>
      </div>
    </div>
  );
}

export default function ChatInterface({ courseId }) {
  const { messages, loading, error, askQuestion, setMessages } = useChat(courseId);
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [voicePhase, setVoicePhase] = useState("idle");
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
      if (!navigator?.mediaDevices?.getUserMedia) {
        setVoiceStatus("Your browser does not support microphone input.");
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;

      if (typeof MediaRecorder === "undefined") {
        setVoiceStatus("Audio recording is not supported in this browser.");
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
        let phaseTimer = null;
        try {
          setVoicePhase("transcribing");
          setVoiceStatus("Transcribing your voice...");
          const blob = new Blob(audioChunksRef.current, { type: mimeType || "audio/webm" });
          phaseTimer = window.setTimeout(() => {
            setVoicePhase("voice-processing");
            setVoiceStatus("Generating grounded voice answer...");
          }, 900);

          const data = await askClassroomVoiceQuestion(courseId, blob, mimeType || "audio/webm");
          const userId = Date.now();
          const audioMime = data.answerAudioMimeType || "audio/wav";
          const audioDataUrl = data.answerAudioBase64 ? `data:${audioMime};base64,${data.answerAudioBase64}` : "";

          setMessages((prev) => [
            ...prev,
            {
              role: "STUDENT",
              message: data.transcriptOriginal || "[Voice]",
              id: userId,
            },
            {
              role: "AI",
              message: data.answerText || "",
              id: data?.assistantMessage?.id || userId + 1,
              sources: data?.assistantMessage?.sources || [],
              voiceAudioDataUrl: audioDataUrl,
            },
          ]);

          const detectedLabel = data?.detectedLanguageCode || "unknown";
          setVoiceStatus(`Voice response ready (${detectedLabel}).`);
          setVoicePhase("idle");
        } catch (err) {
          const detail =
            err?.response?.data?.detail ||
            err?.response?.data?.error ||
            "We could not process your voice request right now.";
          if (/permission/i.test(detail)) {
            setVoiceStatus("Microphone permission was denied. Please allow mic access and try again.");
          } else if (/transcrib/i.test(detail)) {
            setVoiceStatus("Transcription failed. Please speak clearly and try again.");
          } else {
            setVoiceStatus(detail);
          }
          setVoicePhase("idle");
        } finally {
          if (phaseTimer) {
            clearTimeout(phaseTimer);
          }
        }
      };

      recorder.start();
      setIsRecording(true);
      setVoicePhase("recording");
      setVoiceStatus("Recording... click again to stop.");
    } catch (_e) {
      setVoiceStatus("Microphone permission denied.");
      setVoicePhase("idle");
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
      {voicePhase !== "idle" && (
        <p className="text-muted" style={{ marginBottom: "0.4rem" }}>
          {voicePhase === "recording" ? "Recording audio..." : voicePhase === "transcribing" ? "Transcribing..." : "Voice processing..."}
        </p>
      )}
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

            {msg.role === "AI" && msg.voiceAudioDataUrl && (
              <VoiceResponseCard dataUrl={msg.voiceAudioDataUrl} />
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
