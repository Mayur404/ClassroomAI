import { useState, useRef, useEffect } from "react";
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
  }, [messages]);

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
        id: response.data.id,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        { role: "AI", message: "Sorry, I encountered an error. Please try again.", id: Date.now() + 1 },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="chat-container panel">
      <div className="chat-header">
        <div className="status-indicator"></div>
        <h3>AI Teacher</h3>
      </div>
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask me anything about the course syllabus or policies!</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble ${msg.role === "STUDENT" ? "user" : "ai"}`}>
            <div className="bubble-content">{msg.message}</div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="bubble-sources">
                Source: {msg.sources[0].type}
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
          placeholder="Type your question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isTyping}
        />
        <button type="submit" disabled={isTyping || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
