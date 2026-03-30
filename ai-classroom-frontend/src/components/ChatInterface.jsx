import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import client from "../api/client";

function evidenceSnippets(sources) {
  return (sources || [])
    .filter((item) => item?.type === "references" && item?.snippet)
    .slice(0, 2);
}

export default function ChatInterface({ courseId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  useEffect(() => {
    const saved = localStorage.getItem(`chat_history_${courseId}`);
    if (saved) {
      try {
        setMessages(JSON.parse(saved));
      } catch (e) {
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
    const userMessage = { role: "STUDENT", message: currentInput, id: Date.now() };
    const tempAiId = Date.now() + 1;
    
    // Add user message
    setMessages((prev) => [
      ...prev, 
      userMessage
    ]);
    
    setInput("");
    setIsTyping(true);

    try {
      const token = localStorage.getItem("ai-classroom-token");
      const baseURL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
      
      const response = await fetch(`${baseURL}/courses/${courseId}/chat/stream/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": token ? `Token ${token}` : ""
        },
        body: JSON.stringify({ message: currentInput })
      });

      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }

      // Removed instant dot hiding to let it wait for the first token
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let incomingBuffer = "";
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        incomingBuffer += decoder.decode(value, { stream: true });
        const lines = incomingBuffer.split('\n');
        
        // Keep the last partial line in the buffer
        incomingBuffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.trim().startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'token') {
                setIsTyping(false); // Hide typing dots when first token arrives
                setMessages(prev => {
                  const exists = prev.some(m => m.id === tempAiId);
                  if (exists) {
                    return prev.map(msg => msg.id === tempAiId ? { ...msg, message: msg.message + data.text } : msg);
                  }
                  return [...prev, { role: "AI", message: data.text, id: tempAiId, sources: [] }];
                });
              } else if (data.type === 'sources') {
                setMessages(prev => {
                  const exists = prev.some(m => m.id === tempAiId);
                  if (exists) {
                    return prev.map(msg => msg.id === tempAiId ? { ...msg, sources: data.documents } : msg);
                  }
                  return [...prev, { role: "AI", message: "", id: tempAiId, sources: data.documents }];
                });
              }
            } catch (err) {
              console.error("SSE parse error", err);
            }
          }
        }
      }
    } catch (error) {
      console.error("Chat error:", error);
      setIsTyping(false);
      setMessages((prev) => prev.map(msg => {
        if (msg.id === tempAiId && !msg.message) {
          return { ...msg, message: "Sorry, I encountered an error. Please try again." };
        }
        return msg;
      }));
    }
  };

  const clearChat = () => {
    if (window.confirm("Are you sure you want to clear the chat history?")) {
      setMessages([]);
    }
  };

  return (
    <div className="chat-container panel">
      <div className="chat-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="status-indicator"></div>
          <h3>AI Teacher</h3>
        </div>
        {messages.length > 0 && (
          <button className="btn-clear" onClick={clearChat} title="Clear Chat">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
          </button>
        )}
      </div>
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
        {isTyping && (
          <div className="chat-bubble ai typing">
            <div className="typing-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>
      <form className="chat-input" onSubmit={handleSend}>
        <input
          type="text"
          placeholder="Ask a question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isTyping}
          autoComplete="off"
        />
        <button type="submit" disabled={isTyping || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
