import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";

import client from "../api/client";
import ChatInterface from "../components/ChatInterface";
import FileUpload from "../components/FileUpload";

export default function CoursePage() {
  const courseId = 1; // Single classroom for the demo
  const [activeTab, setActiveTab] = useState("materials");
  const [answers, setAnswers] = useState({});
  const [results, setResults] = useState({});

  const courseQuery = useQuery({
    queryKey: ["course", courseId],
    queryFn: async () => {
      const res = await client.get(`/courses/${courseId}/`);
      return res.data;
    },
    retry: false,
  });

  const assignmentsQuery = useQuery({
    queryKey: ["assignments", courseId],
    queryFn: async () => {
      const res = await client.get(`/courses/${courseId}/assignments/`);
      return res.data;
    },
  });

  const generateAssignment = useMutation({
    mutationFn: async ({ type, title }) => {
      const due = new Date();
      due.setDate(due.getDate() + 7);
      const res = await client.post(`/courses/${courseId}/assignments/generate/`, {
        type,
        title,
        due_date: due.toISOString().split("T")[0],
      });
      return res.data;
    },
    onSuccess: () => assignmentsQuery.refetch(),
  });

  const submitAssignment = useMutation({
    mutationFn: async ({ assignmentId, answersPayload }) => {
      const res = await client.post(`/assignments/${assignmentId}/submissions/`, {
        answers: answersPayload,
      });
      return { assignmentId, data: res.data };
    },
    onSuccess: (res) => {
      setResults((prev) => ({ ...prev, [res.assignmentId]: res.data }));
    },
  });

  const handleAnswerChange = (assignmentId, questionNumber, value) => {
    setAnswers((prev) => ({
      ...prev,
      [assignmentId]: {
        ...(prev[assignmentId] || {}),
        [questionNumber]: value,
      },
    }));
  };

  const syncCourse = () => courseQuery.refetch();

  const hasMaterials = courseQuery.data?.syllabus_parse_status === "SUCCESS";

  const completedCount = useMemo(
    () =>
      courseQuery.data?.schedule_items?.filter((i) => i.status === "COMPLETED")
        .length || 0,
    [courseQuery.data]
  );

  if (courseQuery.isLoading)
    return <div className="loading-screen">Loading your classroom...</div>;

  return (
    <div className="classroom-layout">
      {/* Left: Course content */}
      <div className="classroom-main stack">
        {/* Header */}
        <section className="panel hero compact">
          <p className="eyebrow">My Classroom</p>
          <h2>{courseQuery.data?.name || "AI Learning Space"}</h2>
          {courseQuery.data?.description && (
            <p className="text-muted">{courseQuery.data.description}</p>
          )}
        </section>

        {/* Tab Navigation */}
        <div className="tab-bar">
          <button
            className={`tab ${activeTab === "materials" ? "active" : ""}`}
            onClick={() => setActiveTab("materials")}
          >
            📄 Materials
          </button>
          <button
            className={`tab ${activeTab === "path" ? "active" : ""}`}
            onClick={() => setActiveTab("path")}
          >
            🗺️ Learning Path
          </button>
          <button
            className={`tab ${activeTab === "assignments" ? "active" : ""}`}
            onClick={() => setActiveTab("assignments")}
          >
            📝 Assignments
          </button>
        </div>

        {/* TAB: Materials */}
        {activeTab === "materials" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>Study Materials</h3>
              {courseQuery.data?.syllabus_parse_status && (
                <span
                  className={`chip status-${courseQuery.data.syllabus_parse_status.toLowerCase()}`}
                >
                  {courseQuery.data.syllabus_parse_status}
                </span>
              )}
            </div>
            <p className="text-muted">
              Upload a PDF (syllabus, textbook chapter, notes). The AI will
              analyze it and build your learning path.
            </p>
            <FileUpload courseId={courseId} onUploadSuccess={syncCourse} />

            {hasMaterials && (
              <div className="material-summary">
                <h4>Extracted Topics</h4>
                <div className="topic-tags">
                  {courseQuery.data.extracted_topics?.map((t, i) => (
                    <span key={i} className="topic-tag">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* TAB: Learning Path */}
        {activeTab === "path" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>Learning Path</h3>
              <span className="chip">
                {completedCount}/{courseQuery.data?.schedule_items?.length || 0}{" "}
                done
              </span>
            </div>

            {(courseQuery.data?.schedule_items || []).length === 0 ? (
              <p className="empty-state">
                No learning path yet. Upload study materials first!
              </p>
            ) : (
              <div className="schedule-list stack compact">
                {courseQuery.data.schedule_items.map((item) => (
                  <div key={item.id} className="schedule-item">
                    <div className="schedule-number">
                      {item.class_number}
                    </div>
                    <div className="schedule-content">
                      <strong>{item.topic}</strong>
                      <div className="subtopics-list">
                        {item.subtopics?.map((s, i) => (
                          <span key={i} className="subtopic-tag">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <span
                      className={`chip status-${item.status.toLowerCase()}`}
                    >
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* TAB: Assignments */}
        {activeTab === "assignments" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>Assignments</h3>
            </div>

            {hasMaterials ? (
              <div className="assignment-actions">
                <button
                  className="btn-secondary"
                  onClick={() =>
                    generateAssignment.mutate({
                      type: "MCQ",
                      title: "Quick Quiz",
                    })
                  }
                  disabled={generateAssignment.isPending}
                >
                  {generateAssignment.isPending
                    ? "Generating..."
                    : "🧠 Generate MCQ Quiz"}
                </button>
                <button
                  className="btn-secondary"
                  onClick={() =>
                    generateAssignment.mutate({
                      type: "ESSAY",
                      title: "Essay Assignment",
                    })
                  }
                  disabled={generateAssignment.isPending}
                >
                  {generateAssignment.isPending
                    ? "Generating..."
                    : "✍️ Generate Essay"}
                </button>
              </div>
            ) : (
              <p className="empty-state">
                Upload study materials first to generate assignments.
              </p>
            )}

            {generateAssignment.isError && (
              <div className="error-message">
                Failed to generate assignment. Try again.
              </div>
            )}

            <div className="assignments-list stack compact">
              {(assignmentsQuery.data || []).map((a) => {
                const isSubmitted = !!results[a.id];
                const resultData = results[a.id];
                
                return (
                  <div key={a.id} className="assignment-card panel">
                    <div className="assignment-header">
                      <span className="assignment-type">{a.type}</span>
                      <strong>{a.title}</strong>
                    </div>
                    <p className="text-muted">{a.description}</p>
                    {a.questions && a.questions.length > 0 && (
                      <div className="questions-list">
                        {a.questions.map((q, qi) => (
                          <div key={qi} className="question-item">
                            <p>
                              <strong>Q{q.question_number}:</strong> {q.prompt}
                            </p>
                            {q.options && q.options.length > 0 ? (
                              <div className="options-list">
                                {q.options.map((opt, oi) => (
                                  <label key={oi} className="option-label">
                                    <input
                                      type="radio"
                                      name={`q_${a.id}_${q.question_number}`}
                                      value={opt}
                                      checked={answers[a.id]?.[q.question_number] === opt}
                                      onChange={() =>
                                        handleAnswerChange(a.id, q.question_number, opt)
                                      }
                                      disabled={isSubmitted || submitAssignment.isPending}
                                    />
                                    {opt}
                                  </label>
                                ))}
                              </div>
                            ) : (
                              <textarea
                                className="input-field"
                                rows="3"
                                placeholder="Type your answer here..."
                                value={answers[a.id]?.[q.question_number] || ""}
                                onChange={(e) =>
                                  handleAnswerChange(a.id, q.question_number, e.target.value)
                                }
                                disabled={isSubmitted || submitAssignment.isPending}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    
                    {isSubmitted ? (
                      <div className="grading-result panel compact">
                        <h4>Grading Results</h4>
                        <div className="grading-score">
                          Score: <strong>{resultData.ai_grade}</strong> / {a.total_marks}
                        </div>
                        <p className="text-muted">{resultData.ai_feedback?.overall_feedback}</p>
                      </div>
                    ) : (
                      <div className="assignment-footer">
                        <span className="chip">{a.total_marks} marks</span>
                        <button 
                          className="btn-primary" 
                          onClick={() => submitAssignment.mutate({ assignmentId: a.id, answersPayload: answers[a.id] || {} })}
                          disabled={submitAssignment.isPending}
                        >
                          {submitAssignment.isPending && submitAssignment.variables?.assignmentId === a.id ? "Submitting..." : "Submit Answers"}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
              {(!assignmentsQuery.data ||
                assignmentsQuery.data.length === 0) && (
                <p className="empty-state">
                  No assignments yet. Generate one above!
                </p>
              )}
            </div>
          </section>
        )}
      </div>

      {/* Right: Chat */}
      <aside className="classroom-chat">
        <ChatInterface courseId={courseId} />
      </aside>
    </div>
  );
}
