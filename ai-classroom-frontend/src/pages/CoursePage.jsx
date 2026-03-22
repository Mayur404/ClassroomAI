import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import client from "../api/client";
import ChatInterface from "../components/ChatInterface";
import FileUpload from "../components/FileUpload";

export default function CoursePage() {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
    enabled: !!courseId,
  });

  const assignmentsQuery = useQuery({
    queryKey: ["assignments", courseId],
    queryFn: async () => {
      const res = await client.get(`/courses/${courseId}/assignments/`);
      return res.data;
    },
    enabled: !!courseId,
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

  const deleteCourse = useMutation({
    mutationFn: async () => {
      await client.delete(`/courses/${courseId}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries(["courses"]);
      navigate("/");
    },
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

  const deleteMaterial = useMutation({
    mutationFn: async (materialId) => {
      await client.delete(`/materials/${materialId}/delete/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries(["course", courseId]);
      queryClient.invalidateQueries(["courses"]); // Update completed class counts in sidebar
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

  const syncCourse = () => {
    queryClient.invalidateQueries(["course", courseId]);
  };

  const hasMaterials = courseQuery.data?.materials?.length > 0;

  const completedCount = useMemo(
    () =>
      courseQuery.data?.schedule_items?.filter((i) => i.status === "COMPLETED")
        .length || 0,
    [courseQuery.data]
  );

  if (!courseId) return <div className="loading-screen">Select a classroom from the sidebar.</div>;
  if (courseQuery.isLoading)
    return <div className="loading-screen">Loading your classroom...</div>;

  return (
    <div className="classroom-layout">
      {/* Left: Course content */}
      <div className="classroom-main stack">
        {/* Header */}
        <section className="panel hero compact" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <p className="eyebrow">My Classroom</p>
            <h2>{courseQuery.data?.name || "AI Learning Space"}</h2>
            {courseQuery.data?.description && (
              <p className="text-muted">{courseQuery.data.description}</p>
            )}
          </div>
          <button 
            className="btn-secondary text-danger" 
            style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem', borderColor: 'rgba(239, 68, 68, 0.3)' }}
            disabled={deleteCourse.isPending}
            onClick={() => {
              if (window.confirm("Are you sure you want to delete this entire classroom? This action cannot be undone.")) {
                deleteCourse.mutate();
              }
            }}
          >
            {deleteCourse.isPending ? "Deleting..." : "Delete Classroom"}
          </button>
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
              <span className="chip">
                {courseQuery.data?.materials?.length || 0} files
              </span>
            </div>
            
            {hasMaterials && (
              <div className="material-list stack compact">
                {courseQuery.data.materials.map((mat) => (
                  <div key={mat.id} className="material-card">
                    <div className="material-info">
                      <strong>{mat.title}</strong>
                      <span className={`chip status-${mat.parse_status?.toLowerCase() || 'pending'}`}>
                        {mat.parse_status || 'Parsed'}
                      </span>
                    </div>
                    {mat.extracted_topics?.length > 0 && (
                      <p className="text-muted text-small truncate">
                        Topics: {mat.extracted_topics.slice(0, 3).join(", ")}
                        {mat.extracted_topics.length > 3 ? "..." : ""}
                      </p>
                    )}
                    <button 
                      className="btn-icon text-danger"
                      onClick={() => {
                        if (confirm(`Remove "${mat.title}"? This will rebuild the schedule and clear its chat context.`)) {
                          deleteMaterial.mutate(mat.id);
                        }
                      }}
                      disabled={deleteMaterial.isPending && deleteMaterial.variables === mat.id}
                      title="Delete Material"
                    >
                      {deleteMaterial.isPending && deleteMaterial.variables === mat.id ? "..." : "🗑️"}
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="upload-container">
              <h4>Add New Material</h4>
              <p className="text-muted text-small">
                Upload PDFs or paste text. The AI will analyze them and update your learning path.
              </p>
              <FileUpload courseId={courseId} onUploadSuccess={syncCourse} />
            </div>
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
