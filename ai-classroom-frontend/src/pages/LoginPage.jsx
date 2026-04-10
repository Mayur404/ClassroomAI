import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

function getAuthErrorMessage(err) {
  const data = err?.response?.data;

  if (typeof data?.detail === "string" && data.detail.trim()) {
    return data.detail;
  }

  if (typeof data?.error === "string" && data.error.trim()) {
    return data.error;
  }

  if (data?.error && typeof data.error === "object") {
    const firstFieldError = Object.values(data.error).find((value) => Array.isArray(value) && value.length);
    if (firstFieldError) {
      return firstFieldError[0];
    }
  }

  if (Array.isArray(data?.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors[0];
  }

  return "Authentication failed. Please try again.";
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("STUDENT");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Please enter your email.");
      return;
    }
    if (!password.trim()) {
      setError("Please enter your password.");
      return;
    }
    if (mode === "register" && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (mode === "register" && !name.trim()) {
      setError("Please enter your name.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (mode === "register") {
        await register({
          name: name.trim(),
          email: email.trim(),
          password,
          role,
        });
      } else {
        await login({
          email: email.trim(),
          password,
        });
      }
      navigate("/");
    } catch (err) {
      setError(getAuthErrorMessage(err));
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-card panel stack">
        <div className="login-header">
          <p className="eyebrow">AI Classroom</p>
          <h2>{mode === "register" ? "Create your classroom identity" : "Welcome back"}</h2>
          <p className="text-muted">
            {mode === "register"
              ? "Set up your teacher or student access in a couple of quick steps."
              : "Sign in to continue into your class workspace, tutoring tools, and study flow."}
          </p>
        </div>
        <div className="login-mode-switch" role="tablist" aria-label="Authentication mode">
          <button type="button" className={mode === "login" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("login")}>Sign In</button>
          <button type="button" className={mode === "register" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("register")}>Register</button>
        </div>
        {error && <div className="error-message">{error}</div>}
        <form className="stack compact" onSubmit={handleSubmit}>
          {mode === "register" && (
            <div className="form-group">
              <label htmlFor="name">Your Name</label>
              <input
                id="name"
                type="text"
                placeholder="Enter your full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>
          )}
          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus={mode !== "register"}
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              placeholder={mode === "register" ? "Create a secure password" : "Enter your password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={mode === "register" ? 8 : undefined}
            />
          </div>
          {mode === "register" && (
            <div className="form-group">
              <label htmlFor="role">Role</label>
              <select id="role" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="STUDENT">Student</option>
                <option value="TEACHER">Teacher</option>
              </select>
            </div>
          )}
          <button type="submit" disabled={loading} className="btn-primary btn-full">
            {loading ? "Please wait..." : mode === "register" ? "Create Account" : "Sign In"}
          </button>
        </form>
        <p className="login-footer-note">
          {mode === "register"
            ? "You can switch roles later by creating the right account type for your classroom workflow."
            : "Use the same account to keep your classes, notebooks, quizzes, and voice history in one place."}
        </p>
      </section>
    </div>
  );
}
