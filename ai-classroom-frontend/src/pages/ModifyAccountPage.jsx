import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import client from "../api/client";

export default function ModifyAccountPage() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState({ text: "", type: "" });

  useEffect(() => {
    if (user) {
      setName(user.name || "");
      setEmail(user.email || "");
    }
  }, [user]);

  const handleSave = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setMessage({ text: "", type: "" });

    try {
      const res = await client.patch("/auth/me/", {
        name,
      });
      setUser(res.data);
      setMessage({ text: "Account updated successfully.", type: "success" });
    } catch (err) {
      setMessage({
        text: err.response?.data?.detail || "Failed to update account.",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <h2>Modify Account</h2>
        <p className="text-muted" style={{ marginBottom: "1.5rem" }}>Update your profile information.</p>
        
        {message.text && (
          <div className={message.type === "success" ? "toast success" : "toast error"} style={{ padding: "0.5rem 1rem", borderRadius: "var(--radius)", marginBottom: "1rem", backgroundColor: message.type === "error" ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)', color: message.type === "error" ? '#ef4444' : '#22c55e', border: `1px solid ${message.type === "error" ? '#ef4444' : '#22c55e'}`}}>
            {message.text}
          </div>
        )}

        <form onSubmit={handleSave} className="stack" style={{ maxWidth: '400px' }}>
          <div className="field">
            <label>Name</label>
            <input
              type="text"
              className="input-field"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label>Email</label>
            <input
              type="email"
              className="input-field"
              value={email}
              disabled
              title="Email cannot be changed"
              style={{ opacity: 0.7, cursor: 'not-allowed' }}
            />
          </div>
          <div className="field">
            <label>Role</label>
            <input
              type="text"
              className="input-field"
              value={user?.role || ""}
              disabled
              style={{ opacity: 0.7, cursor: 'not-allowed' }}
            />
          </div>
          <div style={{ marginTop: '1rem' }}>
            <button
              type="submit"
              className="btn-primary"
              disabled={isSaving}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {isSaving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
