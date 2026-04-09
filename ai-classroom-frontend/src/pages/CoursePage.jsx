import { useMemo, useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import client from "../api/client";
import ChatInterface from "../components/ChatInterface";
import FileUpload from "../components/FileUpload";
import { useAuth } from "../contexts/AuthContext";

export default function CoursePage() {
  const { user } = useAuth();
  const isTeacher = user?.role === "TEACHER";
  const isStudent = user?.role === "STUDENT";
  const { courseId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState("stream");
  const [answers, setAnswers] = useState({});
  const [results, setResults] = useState({});
  const [precheckResults, setPrecheckResults] = useState({});
  const [labTopic, setLabTopic] = useState("");
  const [labScopeMode, setLabScopeMode] = useState("single");
  const [labSelectedModules, setLabSelectedModules] = useState([]);
  const [labGeneratedQuizId, setLabGeneratedQuizId] = useState(null);
  const [labActiveQuizId, setLabActiveQuizId] = useState(null);
  const [labAttemptState, setLabAttemptState] = useState(null);
  const [labQuizAnswers, setLabQuizAnswers] = useState({});
  const [labQuizResult, setLabQuizResult] = useState(null);
  const [flashcardResults, setFlashcardResults] = useState([]);
  const [flashcardIndex, setFlashcardIndex] = useState(0);
  const [flashcardReveal, setFlashcardReveal] = useState(false);
  const [editingAssignmentId, setEditingAssignmentId] = useState(null);
  const [draftEdit, setDraftEdit] = useState({});
  const [manualAssignment, setManualAssignment] = useState({
    title: "",
    description: "",
    type: "MCQ",
    total_marks: 100,
    due_date: "",
    assignment_pdf: null,
  });

  const courseQuery = useQuery({
    queryKey: ["course", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/`)).data,
    enabled: !!courseId,
    retry: false,
  });

  useEffect(() => {
    const modules = courseQuery.data?.schedule_items || [];
    if (modules.length === 0) return;
    if (labSelectedModules.length === 0) {
      setLabSelectedModules([modules[0].id]);
    }
  }, [courseQuery.data, labSelectedModules.length]);

  const assignmentsQuery = useQuery({
    queryKey: ["assignments", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/assignments/`)).data,
    enabled: !!courseId,
  });

  const quizzesQuery = useQuery({
    queryKey: ["quizzes", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/quizzes/`)).data,
    enabled: !!courseId,
  });

  const peopleQuery = useQuery({
    queryKey: ["course-people", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/people/`)).data,
    enabled: !!courseId,
  });

  const deleteCourse = useMutation({
    mutationFn: async () => client.delete(`/courses/${courseId}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      navigate("/");
    },
  });

  const rotateInviteCode = useMutation({
    mutationFn: async () => (await client.post(`/courses/${courseId}/invite-code/rotate/`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course", courseId] });
      queryClient.invalidateQueries({ queryKey: ["course-people", courseId] });
    },
  });

  const deleteMaterial = useMutation({
    mutationFn: async (materialId) => (await client.delete(`/materials/${materialId}/delete/`)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(["course", courseId], data);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });

  const generateAssignment = useMutation({
    mutationFn: async ({ type, title }) => {
      const due = new Date();
      due.setDate(due.getDate() + 7);
      return (
        await client.post(`/courses/${courseId}/assignments/generate/`, {
          type,
          title,
          due_date: due.toISOString().split("T")[0],
        })
      ).data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });

  const updateAssignment = useMutation({
    mutationFn: async ({ assignmentId, payload }) => (await client.patch(`/assignments/${assignmentId}/`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
      setEditingAssignmentId(null);
    },
  });

  const publishAssignment = useMutation({
    mutationFn: async (assignmentId) => (await client.post(`/assignments/${assignmentId}/publish/`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });

  const deleteAssignment = useMutation({
    mutationFn: async (assignmentId) => {
      await client.delete(`/assignments/${assignmentId}/`);
      return assignmentId;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });

  const submitAssignment = useMutation({
    mutationFn: async ({ assignmentId, answersPayload }) => {
      const res = await client.post(`/assignments/${assignmentId}/submissions/`, { answers: answersPayload });
      return { assignmentId, data: res.data };
    },
    onSuccess: ({ assignmentId, data }) => {
      setResults((prev) => ({ ...prev, [assignmentId]: data }));
    },
  });

  const precheckAssignment = useMutation({
    mutationFn: async ({ assignmentId, answersPayload }) => {
      const res = await client.post(`/assignments/${assignmentId}/precheck/`, { answers: answersPayload });
      return { assignmentId, data: res.data };
    },
    onSuccess: ({ assignmentId, data }) => {
      setPrecheckResults((prev) => ({ ...prev, [assignmentId]: data }));
    },
  });

  const deleteSubmission = useMutation({
    mutationFn: async ({ submissionId }) => client.delete(`/submissions/${submissionId}/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });

  const generatePracticeQuizFromLab = useMutation({
    mutationFn: async () => {
      const scheduleItems = courseQuery.data?.schedule_items || [];
      const allModuleIds = scheduleItems.map((item) => item.id);
      const selectedIds =
        labScopeMode === "multiple"
          ? labSelectedModules
          : [labSelectedModules[0]].filter(Boolean);

      const activeIds = selectedIds.length > 0 ? selectedIds : allModuleIds.slice(0, 1);
      const anchorSessionId = activeIds[0];
      if (!anchorSessionId) {
        throw new Error("No modules available.");
      }

      return (
        await client.post(`/courses/${courseId}/sessions/${anchorSessionId}/practice-quizzes/generate/`, {
          question_count: 8,
          module_scope: labScopeMode,
          include_all_modules: false,
          session_ids: activeIds,
          title: labTopic.trim() ? `Practice: ${labTopic.trim()}` : "Practice Quiz",
        })
      ).data;
    },
    onSuccess: (data) => {
      setLabGeneratedQuizId(data?.id || null);
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  const generateFlashcards = useMutation({
    mutationFn: async () => {
      const scheduleItems = courseQuery.data?.schedule_items || [];
      const selectedIds =
        labScopeMode === "multiple"
          ? labSelectedModules
          : [labSelectedModules[0]].filter(Boolean);

      const topicScope = scheduleItems
        .filter((item) => selectedIds.includes(item.id))
        .map((item) => item.topic)
        .filter(Boolean);

      const allTopics = topicScope.length > 0 ? topicScope : scheduleItems.map((item) => item.topic).filter(Boolean);

      return (
        await client.post(`/courses/${courseId}/study-tools/`, {
          mode: "flashcards",
          module_scope: labScopeMode,
          include_all_modules: false,
          topics: allTopics,
          topic: allTopics[0] || "Module revision",
        })
      ).data;
    },
    onSuccess: (data) => {
      const cards = data?.flashcards || [];
      setFlashcardResults(cards);
      setFlashcardIndex(0);
      setFlashcardReveal(false);
    },
  });

  const manualAssignmentCreate = useMutation({
    mutationFn: async (payload) => {
      const formData = new FormData();
      formData.append("title", payload.title || "");
      formData.append("description", payload.description || "");
      formData.append("type", payload.type || "ESSAY");
      formData.append("total_marks", String(payload.total_marks || 100));
      formData.append("due_date", payload.due_date || "");
      if (payload.assignment_pdf) formData.append("assignment_pdf", payload.assignment_pdf);
      return (
        await client.post(`/courses/${courseId}/assignments/manual/`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments", courseId] });
      setManualAssignment({
        title: "",
        description: "",
        type: "MCQ",
        total_marks: 100,
        due_date: "",
        assignment_pdf: null,
      });
    },
  });

  const hasMaterials = (courseQuery.data?.materials || []).length > 0;
  const moduleItems = courseQuery.data?.schedule_items || [];
  const teacherPublishedQuizzes = (quizzesQuery.data || []).filter((quiz) => quiz.mode === "LIVE" && quiz.state === "PUBLISHED");
  const studentPracticeQuizzes = (quizzesQuery.data || []).filter((quiz) => quiz.mode === "PRACTICE");

  const labQuizDetailQuery = useQuery({
    queryKey: ["lab-quiz-detail", labActiveQuizId],
    queryFn: async () => (await client.get(`/quizzes/${labActiveQuizId}/`)).data,
    enabled: isStudent && !!labActiveQuizId,
  });

  const startLabAttempt = useMutation({
    mutationFn: async (quizId) => (await client.post(`/quizzes/${quizId}/attempts/start/`, {})).data,
    onSuccess: (data) => {
      setLabAttemptState(data);
      setLabQuizAnswers({});
      setLabQuizResult(null);
    },
  });

  const submitLabAttempt = useMutation({
    mutationFn: async () => {
      if (!labAttemptState?.attempt_id) throw new Error("No active attempt.");
      return (await client.post(`/attempts/${labAttemptState.attempt_id}/submit/`, { answers: labQuizAnswers })).data;
    },
    onSuccess: (data) => {
      setLabQuizResult(data);
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  useEffect(() => {
    if (labGeneratedQuizId) {
      setLabActiveQuizId(labGeneratedQuizId);
    }
  }, [labGeneratedQuizId]);

  useEffect(() => {
    if (!labActiveQuizId && studentPracticeQuizzes.length > 0) {
      setLabActiveQuizId(studentPracticeQuizzes[0].id);
    }
  }, [labActiveQuizId, studentPracticeQuizzes]);

  const materialViewUrl = (filePath) => {
    if (!filePath) return "";
    if (String(filePath).startsWith("http://") || String(filePath).startsWith("https://")) return filePath;
    const apiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
    const apiOrigin = new URL(apiBase).origin;
    return `${apiOrigin}${filePath}`;
  };

  const syncCourse = (courseData) => {
    if (courseData) queryClient.setQueryData(["course", courseId], courseData);
    queryClient.invalidateQueries({ queryKey: ["courses"] });
  };

  const handleAnswerChange = (assignmentId, questionNumber, value) => {
    setAnswers((prev) => ({
      ...prev,
      [assignmentId]: {
        ...(prev[assignmentId] || {}),
        [questionNumber]: value,
      },
    }));
  };

  const toggleLabModule = (moduleId) => {
    setLabSelectedModules((prev) => {
      if (prev.includes(moduleId)) {
        const next = prev.filter((id) => id !== moduleId);
        return next.length > 0 ? next : [moduleId];
      }
      return [...prev, moduleId];
    });
  };

  const ratingFromPercent = (value, maxMarks) => {
    const numeric = Number(value || 0);
    const max = Number(maxMarks || 0);
    const percent = max > 0 ? (numeric / max) * 100 : 0;
    if (percent >= 90) return "Excellent";
    if (percent >= 75) return "Strong";
    if (percent >= 60) return "Moderate";
    if (percent >= 40) return "Needs Improvement";
    return "High Risk";
  };

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

  const sections = useMemo(() => {
    const base = [
      { key: "stream", label: "Stream" },
      { key: "classwork", label: "Classwork" },
      { key: "ai", label: "AI Tutor" },
      { key: "people", label: "People" },
    ];
    if (isStudent) {
      base.push({ key: "lab", label: "Lab" });
    }
    return base;
  }, [isStudent]);

  if (!courseId) return <div className="loading-screen">Select a classroom from the sidebar.</div>;
  if (courseQuery.isLoading) return <div className="loading-screen">Loading classroom...</div>;

  return (
    <div className="classroom-layout">
      <div className="classroom-main stack">
        <section className="panel hero compact" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <p className="eyebrow">My Classroom</p>
            <h2>{courseQuery.data?.name || "AI Learning Space"}</h2>
            {courseQuery.data?.description && <p className="text-muted">{courseQuery.data.description}</p>}
          </div>
          {isTeacher && (
            <button
              className="btn-secondary text-danger"
              style={{ padding: "0.4rem 0.75rem", fontSize: "0.8rem", borderColor: "rgba(239, 68, 68, 0.3)" }}
              disabled={deleteCourse.isPending}
              onClick={() => {
                if (window.confirm("Delete this classroom permanently?")) {
                  deleteCourse.mutate();
                }
              }}
            >
              {deleteCourse.isPending ? "Deleting..." : "Delete Classroom"}
            </button>
          )}
        </section>

        <div className="tab-bar">
          {sections.map((tab) => (
            <button
              key={tab.key}
              className={`tab ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", justifyContent: "center" }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "stream" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>Classroom Stream</h3>
              <span className="chip">{courseQuery.data?.materials?.length || 0} materials</span>
            </div>
            <div className="panel compact">
              <p className="eyebrow">Classroom Code</p>
              <h3 style={{ marginBottom: "0.5rem" }}>{peopleQuery.data?.invite_code || courseQuery.data?.invite_code || "------"}</h3>
              <div className="actions">
                <button className="btn-secondary" onClick={() => navigator.clipboard.writeText(peopleQuery.data?.invite_code || courseQuery.data?.invite_code || "")}>Copy Code</button>
                {isTeacher && (
                  <button className="btn-secondary" onClick={() => rotateInviteCode.mutate()} disabled={rotateInviteCode.isPending}>
                    {rotateInviteCode.isPending ? "Rotating..." : "Rotate Code"}
                  </button>
                )}
              </div>
            </div>

            {hasMaterials && (
              <div className="material-list stack compact">
                {courseQuery.data.materials.map((mat) => (
                  <div key={mat.id} className="material-card">
                    <div className="material-info">
                      <strong>{mat.title}</strong>
                      {isTeacher && (
                        <span className={`chip status-${mat.parse_status?.toLowerCase() || "pending"}`}>
                          {mat.parse_status || "Parsed"}
                        </span>
                      )}
                    </div>
                    {isTeacher && (
                      <button
                        className="btn-icon text-danger"
                        title="Delete Material"
                        onClick={() => {
                          if (window.confirm(`Remove "${mat.title}"?`)) {
                            deleteMaterial.mutate(mat.id);
                          }
                        }}
                        disabled={deleteMaterial.isPending && deleteMaterial.variables === mat.id}
                      >
                        {deleteMaterial.isPending && deleteMaterial.variables === mat.id ? "..." : "✕"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {isTeacher && (
              <div className="upload-container">
                <h4>Add New Material</h4>
                <FileUpload courseId={courseId} onUploadSuccess={syncCourse} />
              </div>
            )}
          </section>
        )}

        {activeTab === "classwork" && (
          <>
            <section className="panel stack compact">
              <div className="section-header">
                <h3>Class Materials</h3>
                <span className="chip">{courseQuery.data?.materials?.length || 0} uploaded</span>
              </div>

              {!hasMaterials ? (
                <p className="empty-state">No uploaded materials yet.</p>
              ) : (
                <div className="material-list stack compact">
                  {courseQuery.data.materials.map((mat) => {
                    const materialUrl = materialViewUrl(mat.file);
                    const isPdf = materialUrl.toLowerCase().endsWith(".pdf");
                    return (
                      <div key={mat.id} className="material-card stack compact" style={{ alignItems: "stretch" }}>
                        <div className="material-info">
                          <strong>{mat.title}</strong>
                          {isTeacher && (
                            <span className={`chip status-${mat.parse_status?.toLowerCase() || "pending"}`}>
                              {mat.parse_status || "Parsed"}
                            </span>
                          )}
                        </div>
                        <div className="actions">
                          {materialUrl ? (
                            <>
                              <a className="btn-secondary" href={materialUrl} target="_blank" rel="noreferrer">View</a>
                              <a className="btn-secondary" href={materialUrl} download>Download</a>
                            </>
                          ) : (
                            <span className="text-muted">Text-only material</span>
                          )}
                        </div>
                        {isPdf && (
                          <iframe
                            src={materialUrl}
                            title={`Preview ${mat.title}`}
                            style={{ width: "100%", height: "360px", border: "1px solid rgba(148,163,184,0.25)", borderRadius: "0.75rem" }}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {isStudent && (
              <section className="panel stack compact">
                <div className="section-header">
                  <h3>Teacher Quizzes</h3>
                  <span className="chip">{teacherPublishedQuizzes.length} published</span>
                </div>
                {teacherPublishedQuizzes.length === 0 ? (
                  <p className="empty-state">No teacher quiz has been published yet.</p>
                ) : (
                  <div className="stack compact">
                    {teacherPublishedQuizzes.map((quiz) => (
                      <div key={quiz.id} className="material-card">
                        <div className="material-info">
                          <strong>{quiz.title}</strong>
                          <span className="chip">LIVE</span>
                        </div>
                        <p className="text-muted text-small">Session #{quiz.session}</p>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            setActiveTab("lab");
                          }}
                        >
                          Attend Quiz
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            <section className="panel stack compact">
              <div className="section-header">
                <h3>Assignments</h3>
              </div>

              {hasMaterials && isTeacher ? (
                <div className="assignment-actions">
                  <button className="btn-secondary" onClick={() => generateAssignment.mutate({ type: "MCQ", title: "Quiz Draft" })} disabled={generateAssignment.isPending}>Generate Quiz Draft</button>
                </div>
              ) : null}

              <div className="assignments-list stack compact">
                {(assignmentsQuery.data || []).map((a) => {
                  const resultData = results[a.id] || a.latest_submission;
                  const isSubmitted = !!resultData;

                  return (
                    <div key={a.id} className="assignment-card panel">
                      <div className="assignment-header assignment-header-top">
                        <div className="assignment-header-main">
                          <span className="assignment-type">{a.type}</span>
                          <span className={`chip status-${String(a.status || "DRAFT").toLowerCase()}`}>{a.status}</span>
                          <strong>{a.title}</strong>
                        </div>
                        {isTeacher && (
                          <button
                            type="button"
                            className="btn-icon text-danger"
                            title="Delete Assignment"
                            onClick={() => {
                              if (window.confirm(`Delete "${a.title}"?`)) {
                                deleteAssignment.mutate(a.id);
                              }
                            }}
                          >
                            ✕
                          </button>
                        )}
                      </div>

                      {isTeacher && a.status === "DRAFT" && (
                        <div className="actions" style={{ marginBottom: "0.5rem" }}>
                          <button
                            className="btn-secondary"
                            onClick={() => {
                              if (editingAssignmentId === a.id) {
                                setEditingAssignmentId(null);
                                return;
                              }
                              setEditingAssignmentId(a.id);
                              setDraftEdit({
                                title: a.title || "",
                                description: a.description || "",
                                type: a.type || "ESSAY",
                                total_marks: a.total_marks || 100,
                                due_date: (a.due_date || "").slice(0, 10),
                                questions_text: JSON.stringify(a.questions || [], null, 2),
                                rubric_text: JSON.stringify(a.rubric || [], null, 2),
                              });
                            }}
                          >
                            {editingAssignmentId === a.id ? "Close Editor" : "Edit Draft"}
                          </button>
                          <button className="btn-primary" onClick={() => publishAssignment.mutate(a.id)} disabled={publishAssignment.isPending}>Publish</button>
                        </div>
                      )}

                      {isTeacher && editingAssignmentId === a.id && (
                        <div className="panel compact stack" style={{ marginBottom: "0.75rem" }}>
                          <input className="input-field" value={draftEdit.title || ""} onChange={(e) => setDraftEdit((prev) => ({ ...prev, title: e.target.value }))} placeholder="Assignment title" />
                          <textarea className="input-field" rows="3" value={draftEdit.description || ""} onChange={(e) => setDraftEdit((prev) => ({ ...prev, description: e.target.value }))} placeholder="Description" />
                          <div className="actions">
                            <select value={draftEdit.type || "ESSAY"} onChange={(e) => setDraftEdit((prev) => ({ ...prev, type: e.target.value }))}>
                              <option value="MCQ">MCQ</option>
                              <option value="ESSAY">Essay</option>
                            </select>
                            <input type="number" min="1" className="input-field" value={draftEdit.total_marks || 100} onChange={(e) => setDraftEdit((prev) => ({ ...prev, total_marks: Number(e.target.value || 100) }))} />
                            <input type="date" className="input-field" value={draftEdit.due_date || ""} onChange={(e) => setDraftEdit((prev) => ({ ...prev, due_date: e.target.value }))} />
                          </div>
                          <textarea className="input-field" rows="6" value={draftEdit.questions_text || "[]"} onChange={(e) => setDraftEdit((prev) => ({ ...prev, questions_text: e.target.value }))} placeholder="Questions JSON array" />
                          <textarea className="input-field" rows="5" value={draftEdit.rubric_text || "[]"} onChange={(e) => setDraftEdit((prev) => ({ ...prev, rubric_text: e.target.value }))} placeholder="Rubric JSON array" />
                          <button
                            className="btn-primary"
                            onClick={() => {
                              let questionsParsed = [];
                              let rubricParsed = [];
                              try {
                                questionsParsed = JSON.parse(draftEdit.questions_text || "[]");
                                rubricParsed = JSON.parse(draftEdit.rubric_text || "[]");
                              } catch (_err) {
                                window.alert("Invalid questions/rubric JSON.");
                                return;
                              }

                              updateAssignment.mutate({
                                assignmentId: a.id,
                                payload: {
                                  title: draftEdit.title,
                                  description: draftEdit.description,
                                  type: draftEdit.type,
                                  total_marks: draftEdit.total_marks,
                                  due_date: `${draftEdit.due_date}T23:59:59Z`,
                                  questions: Array.isArray(questionsParsed) ? questionsParsed : [],
                                  rubric: Array.isArray(rubricParsed) ? rubricParsed : [],
                                },
                              });
                            }}
                          >
                            Save Draft
                          </button>
                        </div>
                      )}

                      <p className="text-muted">{a.description}</p>
                      {a.assignment_pdf && (
                        <p className="text-muted">
                          <a href={a.assignment_pdf} target="_blank" rel="noreferrer">View Assignment PDF</a>
                        </p>
                      )}

                      {(a.questions || []).length > 0 && (
                        <div className="questions-list">
                          {a.questions.map((q, qi) => (
                            <div key={qi} className="question-item">
                              <p><strong>Q{q.question_number || qi + 1}:</strong> {q.prompt}</p>
                              {q.options && q.options.length > 0 ? (
                                <div className="options-list">
                                  {q.options.map((opt, oi) => (
                                    <label key={oi} className="option-label">
                                      <input
                                        type="radio"
                                        name={`q_${a.id}_${q.question_number || qi + 1}`}
                                        value={opt}
                                        checked={answers[a.id]?.[q.question_number || qi + 1] === opt}
                                        onChange={() => handleAnswerChange(a.id, q.question_number || qi + 1, opt)}
                                        disabled={!isStudent || isSubmitted || submitAssignment.isPending}
                                      />
                                      {opt}
                                    </label>
                                  ))}
                                </div>
                              ) : (
                                <textarea
                                  className="input-field"
                                  rows="3"
                                  value={answers[a.id]?.[q.question_number || qi + 1] || ""}
                                  onChange={(e) => handleAnswerChange(a.id, q.question_number || qi + 1, e.target.value)}
                                  disabled={!isStudent || isSubmitted || submitAssignment.isPending}
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {!isSubmitted ? (
                        <div className="assignment-footer">
                          <span className="chip">{a.total_marks} marks</span>
                          <button
                            className="btn-primary"
                            onClick={() => submitAssignment.mutate({ assignmentId: a.id, answersPayload: answers[a.id] || {} })}
                            disabled={!isStudent || submitAssignment.isPending}
                          >
                            Submit Answers
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() => precheckAssignment.mutate({ assignmentId: a.id, answersPayload: answers[a.id] || {} })}
                            disabled={!isStudent || precheckAssignment.isPending}
                          >
                            Pre-check with AI
                          </button>
                        </div>
                      ) : (
                        <div className="grading-result panel compact">
                          <h4>Submission Result</h4>
                          <div className="grading-score">
                            Score: <strong>{resultData.ai_grade}</strong> / {a.total_marks}
                          </div>
                          {isStudent && (
                            <button
                              className="btn-secondary"
                              onClick={() => {
                                if (!resultData?.id) return;
                                if (window.confirm("Remove current submission and retake?")) {
                                  deleteSubmission.mutate({ submissionId: resultData.id });
                                }
                              }}
                            >
                              Retake
                            </button>
                          )}
                        </div>
                      )}

                      {precheckResults[a.id] && !isSubmitted && (
                        <div className="grading-result panel compact">
                          <h4>Pre-check Preview</h4>
                          <div className="grading-score">
                            Estimated Score: <strong>{precheckResults[a.id].total_score}</strong> / {a.total_marks}
                          </div>
                          <p className="text-muted"><strong>Rating:</strong> {ratingFromPercent(precheckResults[a.id].total_score, a.total_marks)}</p>
                          <p className="text-muted">{precheckResults[a.id].overall_feedback}</p>
                          {(precheckResults[a.id].score_breakdown || []).length > 0 && (
                            <div className="stack compact">
                              {(precheckResults[a.id].score_breakdown || []).slice(0, 6).map((item, idx) => (
                                <div key={idx} className="material-card">
                                  <p className="text-muted text-small">
                                    <strong>Q{item.question_number || idx + 1}:</strong> {item.score || 0} / {item.max_score || 0}
                                  </p>
                                  {item.feedback && <p className="text-muted text-small">{item.feedback}</p>}
                                  {item.reasoning && <p className="text-muted text-small">{item.reasoning}</p>}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                {(!assignmentsQuery.data || assignmentsQuery.data.length === 0) && (
                  <p className="empty-state">{isTeacher ? "No assignments yet." : "No published assignments yet."}</p>
                )}
              </div>
            </section>
          </>
        )}

        {activeTab === "people" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>People</h3>
              <span className="chip">{(peopleQuery.data?.students || []).length} students</span>
            </div>
            <div className="panel compact">
              <p className="eyebrow">Teacher</p>
              <strong>{peopleQuery.data?.teacher?.name || "-"}</strong>
              <p className="text-muted">{peopleQuery.data?.teacher?.email || ""}</p>
            </div>
            <div className="panel compact">
              <p className="eyebrow">Students</p>
              {(peopleQuery.data?.students || []).length === 0 ? (
                <p className="text-muted">No students enrolled yet.</p>
              ) : (
                <div className="stack compact">
                  {(peopleQuery.data?.students || []).map((student) => (
                    <div key={student.id} className="material-card">
                      <div className="material-info">
                        <strong>{student.name}</strong>
                        <span className="chip">Student</span>
                      </div>
                      <p className="text-muted text-small">{student.email}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "ai" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>AI Tutor</h3>
            </div>
            <p className="text-muted">Text chat is English. Voice chat asks your preferred language when you tap Voice.</p>
          </section>
        )}

        {activeTab === "lab" && (
          <section className="panel stack compact">
            <div className="section-header">
              <h3>Classroom Lab</h3>
            </div>

            {isStudent && (
              <div className="lab-two-box-grid">
                <div className="panel compact stack lab-card">
                  <p className="eyebrow">Practice Quiz</p>
                  <div className="actions" style={{ marginTop: 0 }}>
                    <button className={`btn-secondary ${labScopeMode === "single" ? "active-scope" : ""}`} onClick={() => setLabScopeMode("single")}>Single Module</button>
                    <button className={`btn-secondary ${labScopeMode === "multiple" ? "active-scope" : ""}`} onClick={() => setLabScopeMode("multiple")}>Multiple Modules</button>
                  </div>
                  <input className="input-field" placeholder="Optional focus topic" value={labTopic} onChange={(e) => setLabTopic(e.target.value)} />
                  {labScopeMode === "single" ? (
                    <select
                      value={labSelectedModules[0] || ""}
                      onChange={(e) => setLabSelectedModules([Number(e.target.value)])}
                    >
                      {moduleItems.map((item) => (
                        <option key={item.id} value={item.id}>Class {item.class_number}: {item.topic}</option>
                      ))}
                    </select>
                  ) : (
                    <div className="stack compact">
                      <div className="actions" style={{ marginTop: 0 }}>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            const allIds = moduleItems.map((item) => item.id);
                            if (labSelectedModules.length === allIds.length) {
                              setLabSelectedModules(allIds.slice(0, 1));
                            } else {
                              setLabSelectedModules(allIds);
                            }
                          }}
                        >
                          {labSelectedModules.length === moduleItems.length ? "Clear All" : "Select All"}
                        </button>
                      </div>
                      {moduleItems.map((item) => (
                        <label key={item.id} className="option-label">
                          <input
                            type="checkbox"
                            checked={labSelectedModules.includes(item.id)}
                            onChange={() => toggleLabModule(item.id)}
                          />
                          Class {item.class_number}: {item.topic}
                        </label>
                      ))}
                    </div>
                  )}
                  <button
                    className="btn-primary"
                    onClick={() => generatePracticeQuizFromLab.mutate()}
                    disabled={generatePracticeQuizFromLab.isPending || moduleItems.length === 0}
                  >
                    {generatePracticeQuizFromLab.isPending ? "Generating Quiz..." : "Generate Quiz"}
                  </button>
                  {studentPracticeQuizzes.length > 0 && (
                    <>
                      <select
                        value={labActiveQuizId || ""}
                        onChange={(e) => {
                          setLabActiveQuizId(Number(e.target.value));
                          setLabAttemptState(null);
                          setLabQuizResult(null);
                        }}
                      >
                        {studentPracticeQuizzes.map((quiz) => (
                          <option key={quiz.id} value={quiz.id}>{quiz.title}</option>
                        ))}
                      </select>

                      {labQuizDetailQuery.data && (
                        <div className="panel compact stack">
                          <div className="material-info">
                            <strong>{labQuizDetailQuery.data.title}</strong>
                            <span className="chip">PRIVATE</span>
                          </div>

                          {!labAttemptState ? (
                            <button
                              className="btn-secondary"
                              onClick={() => startLabAttempt.mutate(labActiveQuizId)}
                              disabled={startLabAttempt.isPending}
                            >
                              {startLabAttempt.isPending ? "Starting..." : "Start Quiz"}
                            </button>
                          ) : (
                            <>
                              {(labAttemptState.quiz?.questions || labQuizDetailQuery.data.questions || []).map((question) => (
                                <div key={question.id} className="panel compact stack">
                                  <strong>Q{question.order_index}: {question.question_text}</strong>
                                  {(question.options || []).map((opt) => (
                                    <label key={opt.id || opt.option_key} className="option-label">
                                      <input
                                        type="radio"
                                        name={`lab_quiz_${question.id}`}
                                        value={opt.option_key}
                                        checked={labQuizAnswers[String(question.id)] === opt.option_key}
                                        onChange={(e) => setLabQuizAnswers((prev) => ({ ...prev, [String(question.id)]: e.target.value }))}
                                        disabled={!!labQuizResult}
                                      />
                                      {opt.option_key}. {opt.option_text}
                                    </label>
                                  ))}
                                </div>
                              ))}

                              {!labQuizResult && (
                                <button className="btn-primary" onClick={() => submitLabAttempt.mutate()} disabled={submitLabAttempt.isPending}>
                                  {submitLabAttempt.isPending ? "Submitting..." : "Submit Quiz"}
                                </button>
                              )}

                              {labQuizResult && (
                                <div className="panel compact stack">
                                  <p className="eyebrow">Result</p>
                                  <strong>{labQuizResult.score} / {labQuizResult.max_score} ({labQuizResult.percentage}%)</strong>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </>
                  )}
                  {studentPracticeQuizzes.length === 0 && <p className="text-muted">Generate your first quiz to start practicing.</p>}
                </div>

                <div className="panel compact stack lab-card">
                  <p className="eyebrow">Flashcards</p>
                  <button className="btn-primary" onClick={() => generateFlashcards.mutate()} disabled={generateFlashcards.isPending || moduleItems.length === 0}>
                    {generateFlashcards.isPending ? "Generating..." : "Generate Flashcards"}
                  </button>
                  {flashcardResults.length > 0 && (
                    <div className="stack compact flashcard-stage">
                      <strong>Flashcard {flashcardIndex + 1} of {flashcardResults.length}</strong>
                      <div className={`flashcard-qa-card ${flashcardReveal ? "revealed" : ""}`} key={`flashcard-${flashcardIndex}`}>
                        <p><strong>Q:</strong> {flashcardResults[flashcardIndex]?.question}</p>
                        {flashcardReveal && (
                          <div className="flashcard-answer-block">
                            <p><strong>A:</strong> {flashcardResults[flashcardIndex]?.answer}</p>
                          </div>
                        )}
                      </div>
                      <div className="actions">
                        <button className="btn-secondary" onClick={() => setFlashcardReveal((prev) => !prev)}>
                          {flashcardReveal ? "Hide Answer" : "Show Answer"}
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            setFlashcardReveal(false);
                            setFlashcardIndex((prev) => (prev - 1 + flashcardResults.length) % flashcardResults.length);
                          }}
                        >
                          Previous
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            setFlashcardReveal(false);
                            setFlashcardIndex((prev) => (prev + 1) % flashcardResults.length);
                          }}
                        >
                          Next
                        </button>
                      </div>
                      <div className="flashcard-progress">
                        {flashcardResults.map((item, idx) => (
                          <span key={item.id || idx} className={`dot ${idx === flashcardIndex ? "active" : ""}`} />
                        ))}
                      </div>
                    </div>
                  )}
                  {flashcardResults.length === 0 && <p className="text-muted">Generate flashcards to start revision.</p>}
                </div>
              </div>
            )}
          </section>
        )}
      </div>

      <aside className="classroom-chat" style={{ display: activeTab === "ai" ? "block" : "none" }}>
        <ChatInterface courseId={courseId} />
      </aside>
    </div>
  );
}
