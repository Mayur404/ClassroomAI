import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim()) {
      setError("Please fill in both fields.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login({ name: name.trim(), email: email.trim(), role: "STUDENT" });
      navigate("/");
    } catch (err) {
      setError("Login failed. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-card panel">
        <div className="login-header">
          <h2>Welcome to AI-Classroom</h2>
          <p className="text-muted">Enter your details to start learning</p>
        </div>
        {error && <div className="error-message">{error}</div>}
        <form className="stack compact" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">Your Name</label>
            <input
              id="name"
              type="text"
              placeholder=""
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              placeholder=""
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <button type="submit" disabled={loading} className="btn-primary btn-full">
            {loading ? "Signing in..." : "Start Learning →"}
          </button>
        </form>
      </section>
    </div>
  );
}
