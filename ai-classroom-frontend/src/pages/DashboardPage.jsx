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
          <p className="eyebrow">Welcome, {user.name}</p>
          <h2>{user.role === "TEACHER" ? "Teacher Workspace" : "Student Workspace"}</h2>
          <p>
            Upload PDFs, ask grounded questions, build learning paths, and generate assignments using a
            Groq + Sarvam + RAG pipeline.
          </p>
        </div>
        <div className="actions">
          <Link to={primaryHref} className="btn-primary">
            {primaryCourse ? "Open Classroom" : "Create a Classroom"}
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: '4px' }}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </Link>
        </div>
      </section>

      <section className="grid tri">
        <article className="panel feature-card">
          <div className="feature-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          </div>
          <h3>Upload Materials</h3>
          <p>
            Add searchable PDFs, scanned PDFs, or pasted notes. The backend extracts text, runs OCR when
            needed, and builds a structured learning path.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
          </div>
          <h3>Ask Grounded Questions</h3>
          <p>
            The chat experience is retrieval-first, with answers anchored to the uploaded material instead
            of generic model filler.
          </p>
        </article>
        <article className="panel feature-card">
          <div className="feature-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </div>
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
