import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import client from "../api/client";

export default function QuizModule({ courseId, role, scheduleItems = [], presetQuizId = null, onPresetConsumed = null }) {
  const queryClient = useQueryClient();
  const isTeacher = role === "TEACHER";
  const isStudent = role === "STUDENT";
  const normalizeSessionId = (value) => {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? value : parsed;
  };

  const [selectedSessionId, setSelectedSessionId] = useState(scheduleItems?.[0]?.id || "");
  const [scopeMode, setScopeMode] = useState("single");
  const [selectedSessionIds, setSelectedSessionIds] = useState(scheduleItems?.[0]?.id ? [scheduleItems[0].id] : []);
  const [selectedQuizId, setSelectedQuizId] = useState(null);
  const [attemptState, setAttemptState] = useState(null);
  const [studentAnswers, setStudentAnswers] = useState({});
  const [submitResult, setSubmitResult] = useState(null);

  const [newQuestion, setNewQuestion] = useState({
    question_text: "",
    difficulty: "MEDIUM",
    explanation: "",
    optionA: "",
    optionB: "",
    optionC: "",
    optionD: "",
    correct: "A",
  });

  const [editByQuestion, setEditByQuestion] = useState({});

  const quizzesQuery = useQuery({
    queryKey: ["quizzes", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/quizzes/`)).data,
    enabled: !!courseId,
  });

  const alertsQuery = useQuery({
    queryKey: ["quiz-alerts", courseId],
    queryFn: async () => (await client.get(`/courses/${courseId}/quiz-alerts/`)).data,
    enabled: !!courseId && isTeacher,
  });

  const quizDetailQuery = useQuery({
    queryKey: ["quiz-detail", selectedQuizId],
    queryFn: async () => (await client.get(`/quizzes/${selectedQuizId}/`)).data,
    enabled: !!selectedQuizId,
  });

  const analyticsQuery = useQuery({
    queryKey: ["quiz-analytics", selectedQuizId],
    queryFn: async () => (await client.get(`/quizzes/${selectedQuizId}/analytics/`)).data,
    enabled: !!selectedQuizId && isTeacher,
  });

  const generateLiveQuiz = useMutation({
    mutationFn: async () => {
      const allIds = (scheduleItems || []).map((item) => item.id);
      const activeIds =
        scopeMode === "all"
          ? allIds
          : scopeMode === "multiple"
          ? selectedSessionIds
          : [selectedSessionId].filter(Boolean);

      const anchorSessionId = activeIds[0] || selectedSessionId || allIds[0];
      if (!anchorSessionId) {
        throw new Error("Select at least one module.");
      }

      return (
        await client.post(`/courses/${courseId}/sessions/${anchorSessionId}/quizzes/generate/`, {
          question_count: 8,
          low_score_threshold: 60,
          module_scope: scopeMode,
          include_all_modules: scopeMode === "all",
          session_ids: activeIds,
        })
      ).data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      setSelectedQuizId(data.id);
    },
  });

  const generatePracticeQuiz = useMutation({
    mutationFn: async () => {
      const allIds = (scheduleItems || []).map((item) => item.id);
      const activeIds = scopeMode === "multiple" ? selectedSessionIds : [selectedSessionId].filter(Boolean);

      const anchorSessionId = activeIds[0] || selectedSessionId || allIds[0];
      if (!anchorSessionId) {
        throw new Error("Select at least one module.");
      }

      return (
        await client.post(`/courses/${courseId}/sessions/${anchorSessionId}/practice-quizzes/generate/`, {
          question_count: 8,
          module_scope: scopeMode,
          include_all_modules: false,
          session_ids: activeIds,
        })
      ).data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      setSelectedQuizId(data.id);
    },
  });

  const publishQuiz = useMutation({
    mutationFn: async () => (await client.post(`/quizzes/${selectedQuizId}/publish/`)).data,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      queryClient.invalidateQueries({ queryKey: ["quiz-detail", selectedQuizId] });
      setSelectedQuizId(data.id);
    },
  });

  const saveQuestionEdit = useMutation({
    mutationFn: async ({ questionId, payload }) => (await client.patch(`/questions/${questionId}/`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quiz-detail", selectedQuizId] });
    },
  });

  const deleteQuestion = useMutation({
    mutationFn: async (questionId) => client.delete(`/questions/${questionId}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quiz-detail", selectedQuizId] });
    },
  });

  const addQuestion = useMutation({
    mutationFn: async () => {
      const payload = {
        question_text: newQuestion.question_text,
        difficulty: newQuestion.difficulty,
        explanation: newQuestion.explanation,
        options: [
          { option_key: "A", option_text: newQuestion.optionA, is_correct: newQuestion.correct === "A" },
          { option_key: "B", option_text: newQuestion.optionB, is_correct: newQuestion.correct === "B" },
          { option_key: "C", option_text: newQuestion.optionC, is_correct: newQuestion.correct === "C" },
          { option_key: "D", option_text: newQuestion.optionD, is_correct: newQuestion.correct === "D" },
        ],
      };
      return (await client.post(`/quizzes/${selectedQuizId}/questions/`, payload)).data;
    },
    onSuccess: () => {
      setNewQuestion({
        question_text: "",
        difficulty: "MEDIUM",
        explanation: "",
        optionA: "",
        optionB: "",
        optionC: "",
        optionD: "",
        correct: "A",
      });
      queryClient.invalidateQueries({ queryKey: ["quiz-detail", selectedQuizId] });
    },
  });

  const startAttempt = useMutation({
    mutationFn: async (quizId) => (await client.post(`/quizzes/${quizId}/attempts/start/`, {})).data,
    onSuccess: (data) => {
      setAttemptState(data);
      setSubmitResult(null);
      setStudentAnswers({});
    },
  });

  const submitAttempt = useMutation({
    mutationFn: async () => {
      const attemptId = attemptState?.attempt_id;
      if (!attemptId) throw new Error("No active attempt");
      return (await client.post(`/attempts/${attemptId}/submit/`, { answers: studentAnswers })).data;
    },
    onSuccess: (data) => {
      setSubmitResult(data);
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      queryClient.invalidateQueries({ queryKey: ["quiz-alerts", courseId] });
      queryClient.invalidateQueries({ queryKey: ["quiz-analytics", selectedQuizId] });
    },
  });

  const sessionOptions = useMemo(() => {
    return (scheduleItems || []).map((s) => ({ id: s.id, label: `Class ${s.class_number}: ${s.topic}` }));
  }, [scheduleItems]);

  useEffect(() => {
    if (presetQuizId) {
      setSelectedQuizId(presetQuizId);
      if (typeof onPresetConsumed === "function") {
        onPresetConsumed();
      }
    }
  }, [presetQuizId, onPresetConsumed]);

  useEffect(() => {
    if (!selectedSessionId && sessionOptions.length > 0) {
      setSelectedSessionId(sessionOptions[0].id);
      setSelectedSessionIds([sessionOptions[0].id]);
    }
  }, [selectedSessionId, sessionOptions]);

  const visibleQuizzes = quizzesQuery.data || [];
  const teacherQuizzes = visibleQuizzes.filter((quiz) => quiz.mode === "LIVE");
  const studentPracticeQuizzes = visibleQuizzes.filter((quiz) => quiz.mode === "PRACTICE");

  const onEditSeed = (question) => {
    setEditByQuestion((prev) => ({
      ...prev,
      [question.id]: {
        question_text: question.question_text,
        difficulty: question.difficulty,
        explanation: question.explanation,
        options: (question.options || []).map((o) => ({
          option_key: o.option_key,
          option_text: o.option_text,
          is_correct: !!o.is_correct,
        })),
      },
    }));
  };

  const updateEditOption = (questionId, key, value, field = "option_text") => {
    setEditByQuestion((prev) => {
      const current = prev[questionId];
      if (!current) return prev;
      return {
        ...prev,
        [questionId]: {
          ...current,
          options: current.options.map((o) => {
            if (o.option_key !== key) return o;
            return { ...o, [field]: value };
          }),
        },
      };
    });
  };

  const markCorrect = (questionId, key) => {
    setEditByQuestion((prev) => {
      const current = prev[questionId];
      if (!current) return prev;
      return {
        ...prev,
        [questionId]: {
          ...current,
          options: current.options.map((o) => ({ ...o, is_correct: o.option_key === key })),
        },
      };
    });
  };

  const toggleSession = (sessionId) => {
    setSelectedSessionIds((prev) => {
      if (prev.includes(sessionId)) {
        const next = prev.filter((item) => item !== sessionId);
        if (next.length === 0) return [sessionId];
        return next;
      }
      return [...prev, sessionId];
    });
  };

  const toggleAllSessions = () => {
    const allIds = sessionOptions.map((session) => session.id);
    setSelectedSessionIds((prev) => {
      if (prev.length === allIds.length) {
        return allIds.length > 0 ? [allIds[0]] : [];
      }
      return allIds;
    });
  };

  const canGenerateQuiz = scopeMode === "multiple" ? selectedSessionIds.length > 0 : !!selectedSessionId;

  return (
    <section className="panel stack compact">
      <div className="section-header">
        <h3>Class-Isolated Quizzes</h3>
      </div>

      <div className="panel compact stack">
        <p className="eyebrow">Session Scope</p>
        <div className="actions" style={{ marginTop: 0 }}>
          <button className={`btn-secondary ${scopeMode === "single" ? "active-scope" : ""}`} onClick={() => setScopeMode("single")}>Single Module</button>
          <button className={`btn-secondary ${scopeMode === "multiple" ? "active-scope" : ""}`} onClick={() => setScopeMode("multiple")}>Multiple Modules</button>
          {isTeacher && (
            <button className={`btn-secondary ${scopeMode === "all" ? "active-scope" : ""}`} onClick={() => setScopeMode("all")}>All Modules</button>
          )}
        </div>
        <div className="actions">
          {scopeMode === "single" && (
            <select value={selectedSessionId} onChange={(e) => setSelectedSessionId(normalizeSessionId(e.target.value))}>
              {sessionOptions.length === 0 ? (
                <option value="">No sessions available</option>
              ) : (
                sessionOptions.map((session) => (
                  <option key={session.id} value={session.id}>{session.label}</option>
                ))
              )}
            </select>
          )}
          {isTeacher ? (
            <button className="btn-primary" onClick={() => generateLiveQuiz.mutate()} disabled={!canGenerateQuiz || generateLiveQuiz.isPending}>
              {generateLiveQuiz.isPending ? "Generating..." : "Generate Draft Quiz"}
            </button>
          ) : (
            <button className="btn-primary" onClick={() => generatePracticeQuiz.mutate()} disabled={!canGenerateQuiz || generatePracticeQuiz.isPending}>
              {generatePracticeQuiz.isPending ? "Generating..." : "Generate Practice Quiz"}
            </button>
          )}
        </div>
        {scopeMode === "multiple" && (
          <div className="panel compact stack">
            <p className="eyebrow">Choose Modules</p>
            <div className="actions" style={{ marginTop: 0 }}>
              <button className="btn-secondary" onClick={toggleAllSessions}>
                {selectedSessionIds.length === sessionOptions.length ? "Clear All" : "Select All"}
              </button>
            </div>
            <div className="stack compact">
              {sessionOptions.map((session) => (
                <label key={session.id} className="option-label">
                  <input
                    type="checkbox"
                    checked={selectedSessionIds.includes(session.id)}
                    onChange={() => toggleSession(session.id)}
                  />
                  {session.label}
                </label>
              ))}
            </div>
          </div>
        )}
        <p className="text-muted">Questions are generated only from this class session context.</p>
      </div>

      <div className="grid tri">
        <div className="panel compact stack">
          <p className="eyebrow">Teacher Quizzes</p>
          {teacherQuizzes.length === 0 ? (
            <p className="text-muted">No teacher quizzes yet.</p>
          ) : (
            teacherQuizzes.map((quiz) => (
              <div key={quiz.id} className="material-card" style={{ cursor: "pointer" }} onClick={() => setSelectedQuizId(quiz.id)}>
                <div className="material-info">
                  <strong>{quiz.title}</strong>
                  <span className={`chip status-${String(quiz.state || "DRAFT").toLowerCase()}`}>{quiz.state}</span>
                </div>
                <p className="text-muted text-small">Session #{quiz.session}</p>
              </div>
            ))
          )}
        </div>
        {isStudent && (
          <div className="panel compact stack">
            <p className="eyebrow">My Private Practice Quizzes</p>
            {studentPracticeQuizzes.length === 0 ? (
              <p className="text-muted">No private practice quizzes generated yet.</p>
            ) : (
              studentPracticeQuizzes.map((quiz) => (
                <div key={quiz.id} className="material-card" style={{ cursor: "pointer" }} onClick={() => setSelectedQuizId(quiz.id)}>
                  <div className="material-info">
                    <strong>{quiz.title}</strong>
                    <span className="chip">PRIVATE</span>
                  </div>
                  <p className="text-muted text-small">Session #{quiz.session}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {isTeacher && (alertsQuery.data || []).length > 0 && (
        <div className="panel compact stack">
          <p className="eyebrow">Low Score Alerts (&lt; 60%)</p>
          {(alertsQuery.data || []).slice(0, 8).map((alert) => (
            <div key={alert.id} className="material-card">
              <strong>{alert.student_name}</strong>
              <p className="text-muted text-small">Quiz #{alert.quiz} • {alert.actual_percent}%</p>
            </div>
          ))}
        </div>
      )}

      {selectedQuizId && quizDetailQuery.data && isTeacher && (
        <div className="panel compact stack">
          <div className="material-info">
            <strong>{quizDetailQuery.data.title}</strong>
            <span className={`chip status-${String(quizDetailQuery.data.state || "DRAFT").toLowerCase()}`}>{quizDetailQuery.data.state}</span>
          </div>

          {quizDetailQuery.data.mode === "LIVE" && quizDetailQuery.data.state !== "PUBLISHED" && (
            <button className="btn-primary" onClick={() => publishQuiz.mutate()} disabled={publishQuiz.isPending}>
              {publishQuiz.isPending ? "Publishing..." : "Publish Quiz"}
            </button>
          )}

          {(quizDetailQuery.data.questions || []).map((question) => {
            const editState = editByQuestion[question.id];
            return (
              <div key={question.id} className="panel compact stack">
                <div className="material-info">
                  <strong>Q{question.order_index}: {question.question_text}</strong>
                  <span className="chip">{question.status}</span>
                </div>

                {!editState ? (
                  <button className="btn-secondary" onClick={() => onEditSeed(question)}>Review / Edit</button>
                ) : (
                  <>
                    <textarea
                      className="input-field"
                      rows="2"
                      value={editState.question_text}
                      onChange={(e) => setEditByQuestion((prev) => ({ ...prev, [question.id]: { ...editState, question_text: e.target.value } }))}
                    />
                    {editState.options.map((opt) => (
                      <div key={opt.option_key} className="actions">
                        <label>{opt.option_key}</label>
                        <input className="input-field" value={opt.option_text} onChange={(e) => updateEditOption(question.id, opt.option_key, e.target.value)} />
                        <label>
                          <input type="radio" checked={opt.is_correct} onChange={() => markCorrect(question.id, opt.option_key)} /> Correct
                        </label>
                      </div>
                    ))}
                    <textarea
                      className="input-field"
                      rows="2"
                      placeholder="Explanation"
                      value={editState.explanation}
                      onChange={(e) => setEditByQuestion((prev) => ({ ...prev, [question.id]: { ...editState, explanation: e.target.value } }))}
                    />
                    <div className="actions">
                      <button className="btn-primary" onClick={() => saveQuestionEdit.mutate({ questionId: question.id, payload: editState })}>Save</button>
                      <button className="btn-secondary text-danger" onClick={() => deleteQuestion.mutate(question.id)}>Delete</button>
                    </div>
                  </>
                )}
              </div>
            );
          })}

          {quizDetailQuery.data.state !== "PUBLISHED" && (
            <div className="panel compact stack">
              <p className="eyebrow">Add Manual Question</p>
              <textarea className="input-field" rows="2" placeholder="Question" value={newQuestion.question_text} onChange={(e) => setNewQuestion((prev) => ({ ...prev, question_text: e.target.value }))} />
              <div className="actions">
                <input className="input-field" placeholder="Option A" value={newQuestion.optionA} onChange={(e) => setNewQuestion((prev) => ({ ...prev, optionA: e.target.value }))} />
                <input className="input-field" placeholder="Option B" value={newQuestion.optionB} onChange={(e) => setNewQuestion((prev) => ({ ...prev, optionB: e.target.value }))} />
              </div>
              <div className="actions">
                <input className="input-field" placeholder="Option C" value={newQuestion.optionC} onChange={(e) => setNewQuestion((prev) => ({ ...prev, optionC: e.target.value }))} />
                <input className="input-field" placeholder="Option D" value={newQuestion.optionD} onChange={(e) => setNewQuestion((prev) => ({ ...prev, optionD: e.target.value }))} />
              </div>
              <div className="actions">
                <select value={newQuestion.correct} onChange={(e) => setNewQuestion((prev) => ({ ...prev, correct: e.target.value }))}>
                  <option value="A">Correct: A</option>
                  <option value="B">Correct: B</option>
                  <option value="C">Correct: C</option>
                  <option value="D">Correct: D</option>
                </select>
                <button className="btn-primary" onClick={() => addQuestion.mutate()} disabled={addQuestion.isPending || !newQuestion.question_text.trim()}>
                  {addQuestion.isPending ? "Adding..." : "Add Question"}
                </button>
              </div>
            </div>
          )}

          {analyticsQuery.data && (
            <div className="panel compact stack">
              <p className="eyebrow">Teacher Analytics</p>
              <p className="text-muted">Attempts: {analyticsQuery.data.attempt_count} • Avg: {analyticsQuery.data.average_percentage}%</p>
              {(analyticsQuery.data.students || []).map((row) => (
                <div key={`${row.student_id}-${row.submitted_at}`} className="material-card">
                  <strong>{row.student_name}</strong>
                  <p className="text-muted text-small">{row.score}/{row.max_score} ({row.percentage}%)</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {selectedQuizId && quizDetailQuery.data && isStudent && (
        <div className="panel compact stack">
          <div className="material-info">
            <strong>{quizDetailQuery.data.title}</strong>
            <span className={`chip status-${String(quizDetailQuery.data.state || "DRAFT").toLowerCase()}`}>{quizDetailQuery.data.mode}</span>
          </div>

          {!attemptState ? (
            <button className="btn-primary" onClick={() => startAttempt.mutate(selectedQuizId)} disabled={startAttempt.isPending}>
              {startAttempt.isPending ? "Starting..." : "Start Quiz"}
            </button>
          ) : (
            <>
              {((attemptState.quiz?.questions || quizDetailQuery.data.questions || [])).map((question) => (
                <div key={question.id} className="panel compact stack">
                  <strong>Q{question.order_index}: {question.question_text}</strong>
                  {(question.options || []).map((opt) => (
                    <label key={opt.id || opt.option_key} className="option-label">
                      <input
                        type="radio"
                        name={`quiz_${question.id}`}
                        value={opt.option_key}
                        checked={studentAnswers[String(question.id)] === opt.option_key}
                        onChange={(e) => setStudentAnswers((prev) => ({ ...prev, [String(question.id)]: e.target.value }))}
                        disabled={!!submitResult}
                      />
                      {opt.option_key}. {opt.option_text}
                    </label>
                  ))}
                </div>
              ))}

              {!submitResult && (
                <button className="btn-primary" onClick={() => submitAttempt.mutate()} disabled={submitAttempt.isPending}>
                  {submitAttempt.isPending ? "Submitting..." : "Final Submit"}
                </button>
              )}

              {submitResult && (
                <div className="panel compact stack">
                  <p className="eyebrow">Final Result</p>
                  <strong>{submitResult.score} / {submitResult.max_score} ({submitResult.percentage}%)</strong>
                  {(submitResult.results || []).map((res) => (
                    <div key={res.question_id} className="material-card">
                      <strong>{res.is_correct ? "Correct" : "Incorrect"}</strong>
                      <p className="text-muted text-small">Your choice: {res.selected_option_key || "-"}, Correct: {res.correct_option_key}</p>
                      <p className="text-muted text-small">{res.explanation}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
