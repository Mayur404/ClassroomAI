import { useEffect, useMemo, useState } from "react";
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
  const [expandedScheduleItems, setExpandedScheduleItems] = useState({});
  const [expandedAnswerReviews, setExpandedAnswerReviews] = useState({});

  useEffect(() => {
    setExpandedScheduleItems({});
    setExpandedAnswerReviews({});
  }, [courseId]);

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });

  const deleteCourse = useMutation({
    mutationFn: async () => {
      await client.delete(`/courses/${courseId}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
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

  const deleteAssignment = useMutation({
    mutationFn: async (assignmentId) => {
      await client.delete(`/assignments/${assignmentId}/`);
      return assignmentId;
    },
    onSuccess: (assignmentId) => {
      setResults((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      setAnswers((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });

  const deleteSubmission = useMutation({
    mutationFn: async ({ assignmentId, submissionId }) => {
      await client.delete(`/submissions/${submissionId}/`);
      return { assignmentId, submissionId };
    },
    onSuccess: ({ assignmentId }) => {
      setResults((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });

  const deleteMaterial = useMutation({
    mutationFn: async (materialId) => {
      const res = await client.delete(`/materials/${materialId}/delete/`);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["course", courseId], data);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });

  const updateScheduleItem = useMutation({
    mutationFn: async ({ scheduleId, completed }) => {
      const res = await client.post(`/schedule/${scheduleId}/complete/`, {
        completed,
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course", courseId] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
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

  const syncCourse = (courseData) => {
    if (courseData) {
      queryClient.setQueryData(["course", courseId], courseData);
    }
    queryClient.invalidateQueries({ queryKey: ["courses"] });
  };

  const toggleScheduleExpanded = (scheduleId) => {
    setExpandedScheduleItems((prev) => ({
      ...prev,
      [scheduleId]: !prev[scheduleId],
    }));
  };

  const toggleAnswerReview = (assignmentId, questionNumber) => {
    const key = `${assignmentId}-${questionNumber}`;
    setExpandedAnswerReviews((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const hasMaterials = courseQuery.data?.materials?.length > 0;

  useEffect(() => {
    if (!assignmentsQuery.data) return;

    const persistedResults = {};
    const persistedAnswers = {};

    assignmentsQuery.data.forEach((assignment) => {
      if (assignment.latest_submission) {
        persistedResults[assignment.id] = assignment.latest_submission;
        persistedAnswers[assignment.id] = assignment.latest_submission.answers || {};
      }
    });

    if (Object.keys(persistedResults).length > 0) {
      setResults((prev) => ({ ...prev, ...persistedResults }));
    }
    if (Object.keys(persistedAnswers).length > 0) {
      setAnswers((prev) => ({ ...prev, ...persistedAnswers }));
    }
  }, [assignmentsQuery.data]);

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
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', justifyContent: 'center' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            Materials
          </button>
          <button
            className={`tab ${activeTab === "path" ? "active" : ""}`}
            onClick={() => setActiveTab("path")}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', justifyContent: 'center' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21 3 6"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>
            Learning Path
          </button>
          <button
            className={`tab ${activeTab === "assignments" ? "active" : ""}`}
            onClick={() => setActiveTab("assignments")}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', justifyContent: 'center' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            Assignments
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
                      {deleteMaterial.isPending && deleteMaterial.variables === mat.id ? "..." : (
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                      )}
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

            {courseQuery.data?.schedule_items?.length > 0 && (
              <div className="path-summary">
                <div className="path-summary-card">
                  <span className="path-summary-label">Progress</span>
                  <strong>{courseQuery.data?.schedule_progress_percent || 0}% complete</strong>
                </div>
                <div className="path-summary-card">
                  <span className="path-summary-label">Next Up</span>
                  <strong>{courseQuery.data?.next_class_topic || "All done"}</strong>
                </div>
                <div className="path-summary-card">
                  <span className="path-summary-label">Materials</span>
                  <strong>{courseQuery.data?.material_count || 0} source file(s)</strong>
                </div>
              </div>
            )}

            {(courseQuery.data?.schedule_items || []).length === 0 ? (
              <p className="empty-state">
                No learning path yet. Upload study materials first!
              </p>
            ) : (
              <div className="schedule-list stack compact">
                {courseQuery.data.schedule_items.map((item) => (
                  <div
                    key={item.id}
                    className={`schedule-item schedule-item-${item.status.toLowerCase()} ${
                      expandedScheduleItems[item.id] ? "expanded" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="schedule-main"
                      onClick={() => toggleScheduleExpanded(item.id)}
                    >
                      <div className="schedule-number">
                        {item.class_number}
                      </div>
                      <div className="schedule-content">
                        <div className="schedule-title-row">
                          <strong>{item.topic}</strong>
                          <span
                            className={`chip status-${item.status.toLowerCase()}`}
                          >
                            {item.status}
                          </span>
                        </div>
                        <div className="subtopics-list">
                          {item.subtopics?.slice(0, 3).map((s, i) => (
                            <span key={i} className="subtopic-tag">
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                      <span className="schedule-expand-indicator">
                        {expandedScheduleItems[item.id] ? "−" : "+"}
                      </span>
                    </button>

                    {expandedScheduleItems[item.id] && (
                      <div className="schedule-details">
                        <div className="schedule-detail-block">
                          <span className="schedule-detail-label">Focus Areas</span>
                          <div className="schedule-detail-list">
                            {(item.subtopics || []).map((subtopic, index) => (
                              <span key={index} className="subtopic-tag detail">
                                {subtopic}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="schedule-detail-block">
                          <span className="schedule-detail-label">What you should be able to do</span>
                          <ul className="schedule-objectives">
                            {(item.learning_objectives || []).map((objective, index) => (
                              <li key={index}>{objective}</li>
                            ))}
                          </ul>
                        </div>

                        <div className="schedule-details-footer">
                          <span className="chip">{item.duration_minutes} min session</span>
                          <button
                            type="button"
                            className={item.status === "COMPLETED" ? "btn-secondary" : "btn-primary"}
                            onClick={() =>
                              updateScheduleItem.mutate({
                                scheduleId: item.id,
                                completed: item.status !== "COMPLETED",
                              })
                            }
                            disabled={
                              updateScheduleItem.isPending &&
                              updateScheduleItem.variables?.scheduleId === item.id
                            }
                          >
                            {updateScheduleItem.isPending &&
                            updateScheduleItem.variables?.scheduleId === item.id
                              ? "Saving..."
                              : item.status === "COMPLETED"
                              ? "Mark as Pending"
                              : "Mark as Completed"}
                          </button>
                        </div>
                      </div>
                    )}
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
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  {generateAssignment.isPending ? (
                    "Generating..."
                  ) : (
                    <>
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      Generate MCQ Quiz
                    </>
                  )}
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
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  {generateAssignment.isPending ? (
                    "Generating..."
                  ) : (
                    <>
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                      Generate Essay
                    </>
                  )}
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
                const resultData = results[a.id] || a.latest_submission;
                const isSubmitted = !!resultData;
                const reviewByQuestion = Object.fromEntries(
                  (resultData?.score_breakdown || []).map((item) => [
                    String(item.question_number),
                    item,
                  ])
                );
                
                return (
                  <div key={a.id} className="assignment-card panel">
                    <div className="assignment-header assignment-header-top">
                      <div className="assignment-header-main">
                        <span className="assignment-type">{a.type}</span>
                        <strong>{a.title}</strong>
                      </div>
                        <button
                          type="button"
                          className="btn-icon text-danger"
                          title="Delete Assignment"
                          onClick={() => {
                            if (window.confirm(`Delete "${a.title}"? This assignment and its submission history will be removed.`)) {
                              deleteAssignment.mutate(a.id);
                            }
                          }}
                          disabled={deleteAssignment.isPending && deleteAssignment.variables === a.id}
                        >
                          {deleteAssignment.isPending && deleteAssignment.variables === a.id ? "..." : (
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                          )}
                        </button>
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

                            {isSubmitted && (() => {
                              const review = reviewByQuestion[String(q.question_number)];
                              const reviewKey = `${a.id}-${q.question_number}`;
                              if (!review) return null;

                              return (
                                <div className="question-review">
                                  <button
                                    type="button"
                                    className="btn-secondary review-toggle"
                                    onClick={() => toggleAnswerReview(a.id, q.question_number)}
                                  >
                                    {expandedAnswerReviews[reviewKey]
                                      ? "Hide Answer Review"
                                      : "Show Answer Review"}
                                  </button>

                                  {expandedAnswerReviews[reviewKey] && (
                                    <div className="review-panel">
                                      <div className="review-row">
                                        <span className="review-label">Marks</span>
                                        <span className="review-value score">
                                          {review.score} / {review.max_score}
                                        </span>
                                      </div>

                                      {review.student_answer !== undefined && (
                                        <div className="review-row stacked">
                                          <span className="review-label">Your answer</span>
                                          <p className="review-explanation">
                                            {review.student_answer || "No answer submitted"}
                                          </p>
                                        </div>
                                      )}

                                      {a.type === "MCQ" && (
                                        <div className="review-row">
                                          <span className="review-label">Correct answer</span>
                                          <span className="review-value correct">
                                            {review.correct_answer || "Not available"}
                                          </span>
                                        </div>
                                      )}

                                      {(review.reasoning || review.explanation || review.feedback) && (
                                        <div className="review-row stacked">
                                          <span className="review-label">
                                            {a.type === "MCQ" ? "Explanation" : "Reasoning"}
                                          </span>
                                          <p className="review-explanation">
                                            {review.reasoning || review.explanation || review.feedback}
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })()}
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
                        <p className="text-muted">
                          {a.type === "MCQ"
                            ? "Click each question's answer review to see the correct option and explanation."
                            : "Click each question's answer review to see marks, your answer, and grading reasoning."}
                        </p>
                        {a.type !== "MCQ" && resultData.ai_feedback?.overall_feedback && (
                          <p className="text-muted">{resultData.ai_feedback.overall_feedback}</p>
                        )}
                        <div className="grading-actions">
                           <button
                             type="button"
                             className="btn-secondary"
                             onClick={() => {
                               const submissionId = resultData?.id || a.latest_submission?.id;
                               if (!submissionId) return;
                               if (window.confirm(`Remove your current submission for "${a.title}" and retake it?`)) {
                                 deleteSubmission.mutate({ assignmentId: a.id, submissionId });
                               }
                             }}
                             disabled={
                               deleteSubmission.isPending &&
                               deleteSubmission.variables?.assignmentId === a.id
                             }
                           >
                             {deleteSubmission.isPending &&
                             deleteSubmission.variables?.assignmentId === a.id
                               ? "Removing..."
                               : a.type === "MCQ"
                               ? "Retake Quiz"
                               : "Retake Assignment"}
                           </button>
                        </div>
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
