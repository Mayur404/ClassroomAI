import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <div className="stack">
      <section className="panel hero">
        <div>
          <p className="eyebrow">Welcome{user ? `, ${user.name}` : ""}</p>
          <h2>Your Personal AI Tutor</h2>
          <p>
            Upload your study materials, ask questions, and get AI-generated
            assignments — all powered by Google Gemini.
          </p>
        </div>
        <div className="actions">
          {user ? (
            <>
              <Link to="/learn" className="btn-primary">
                Go to Classroom →
              </Link>
              <button className="btn-secondary" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-primary">
              Login to Start →
            </Link>
          )}
        </div>
      </section>

      <section className="grid tri">
        <article className="panel feature-card">
          <div className="feature-icon">📄</div>
          <h3>Upload Materials</h3>
          <p>
            Drop any PDF — syllabus, textbook chapter, or notes. The AI reads
            and structures it into a learning path.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">💬</div>
          <h3>Ask Questions</h3>
          <p>
            Chat with your AI tutor. It answers based strictly on your uploaded
            materials using RAG technology.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">📝</div>
          <h3>Get Assignments</h3>
          <p>
            The AI generates quizzes, essays, and coding problems from your
            materials to test your understanding.
          </p>
        </article>
      </section>
    </div>
  );
}
