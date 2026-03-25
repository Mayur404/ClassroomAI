import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import client from "../api/client";
import { useAuth } from "../contexts/AuthContext";

export default function DashboardPage() {
  const { user, logout } = useAuth();

  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: async () => {
      const res = await client.get("/courses/");
      return res.data;
    },
    enabled: !!user,
  });

  const primaryCourse = coursesQuery.data?.[0] || null;
  const primaryHref = primaryCourse ? `/learn/${primaryCourse.id}` : "/";

  return (
    <div className="stack">
      <section className="panel hero">
        <div>
          <p className="eyebrow">Welcome{user ? `, ${user.name}` : ""}</p>
          <h2>Your Local AI Classroom</h2>
          <p>
            Upload PDFs, ask grounded questions, build learning paths, and generate assignments using a
            local Ollama + RAG pipeline.
          </p>
        </div>
        <div className="actions">
          {user ? (
            <>
              <Link to={primaryHref} className="btn-primary">
                {primaryCourse ? "Open Classroom ->" : "Create a Classroom ->"}
              </Link>
              <button className="btn-secondary" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-primary">
              Login to Start ->
            </Link>
          )}
        </div>
      </section>

      <section className="grid tri">
        <article className="panel feature-card">
          <div className="feature-icon">PDF</div>
          <h3>Upload Materials</h3>
          <p>
            Add searchable PDFs, scanned PDFs, or pasted notes. The backend extracts text, runs OCR when
            needed, and builds a structured learning path.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">Q&A</div>
          <h3>Ask Grounded Questions</h3>
          <p>
            The chat experience is retrieval-first, with answers anchored to the uploaded material instead
            of generic model filler.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">AI</div>
          <h3>Generate Assignments</h3>
          <p>
            Create quizzes, essays, and coding tasks from course content, then grade submissions with
            structured AI feedback.
          </p>
        </article>
      </section>
    </div>
  );
}
