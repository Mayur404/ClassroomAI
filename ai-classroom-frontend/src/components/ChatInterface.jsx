import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import client from "../api/client";

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

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: "STUDENT", message: input, id: Date.now() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsTyping(true);

    try {
      const response = await client.post(`/courses/${courseId}/chat/ask/`, { message: input });
      const aiMessage = {
        role: "AI",
        message: response.data.ai_response,
        sources: response.data.sources,
        id: response.data.id || Date.now() + 1,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        { role: "AI", message: "Sorry, I encountered an error. Please try again.", id: Date.now() + 2 },
      ]);
    } finally {
      setIsTyping(false);
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
            🗑️
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
            {msg.sources && msg.sources.length > 0 && msg.sources[0].num_chunks > 0 && (
              <div className="bubble-sources">
                Researched from {msg.sources[0].num_chunks} section(s) of your documents.
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
