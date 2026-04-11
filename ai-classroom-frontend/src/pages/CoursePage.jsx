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
  const emptyTeacherQuestionDraft = () => ({
    question_text: "",
    explanation: "",
    difficulty: "MEDIUM",
    correct_option_key: "A",
    option_a: "",
    option_b: "",
    option_c: "",
    option_d: "",
  });

  const [activeTab, setActiveTab] = useState("stream");
  const [answers, setAnswers] = useState({});
  const [results, setResults] = useState({});
  const [precheckResults, setPrecheckResults] = useState({});
  const [materialPreviewById, setMaterialPreviewById] = useState({});
  const [classworkQuizSessionId, setClassworkQuizSessionId] = useState(null);
  const [classworkScopeMode, setClassworkScopeMode] = useState("single");
  const [classworkSelectedModules, setClassworkSelectedModules] = useState([]);
  const [classworkQuizTitle, setClassworkQuizTitle] = useState("");
  const [classworkQuizInstructions, setClassworkQuizInstructions] = useState("");
  const [classworkQuizScheduledFor, setClassworkQuizScheduledFor] = useState("");
  const [classworkQuizDueAt, setClassworkQuizDueAt] = useState("");
  const [classworkShuffleQuestions, setClassworkShuffleQuestions] = useState(true);
  const [classworkShuffleOptions, setClassworkShuffleOptions] = useState(true);
  const [activeTeacherQuizId, setActiveTeacherQuizId] = useState(null);
  const [teacherQuizEditMode, setTeacherQuizEditMode] = useState(false);
  const [newTeacherQuestionDraft, setNewTeacherQuestionDraft] = useState(emptyTeacherQuestionDraft());
  const [quizMetaDraft, setQuizMetaDraft] = useState({
    title: "",
    instructions: "",
    scheduled_for: "",
    due_at: "",
    shuffle_questions: true,
    shuffle_options: true,
  });
  const [quizQuestionDrafts, setQuizQuestionDrafts] = useState({});
  const [activeLiveQuizId, setActiveLiveQuizId] = useState(null);
  const [liveAttemptState, setLiveAttemptState] = useState(null);
  const [liveQuizAnswers, setLiveQuizAnswers] = useState({});
  const [liveQuizResult, setLiveQuizResult] = useState(null);
  const [liveQuizSubmissionById, setLiveQuizSubmissionById] = useState({});
  const [quizClock, setQuizClock] = useState(() => Date.now());
  const [labViewType, setLabViewType] = useState(null);
  const [practiceQuizName, setPracticeQuizName] = useState("");
  const [practiceQuestionCount, setPracticeQuestionCount] = useState(8);
  const [labScopeMode, setLabScopeMode] = useState("single");
  const [labSelectedModules, setLabSelectedModules] = useState([]);
  const [labGeneratedQuizId, setLabGeneratedQuizId] = useState(null);
  const [labActiveQuizId, setLabActiveQuizId] = useState(null);
  const [labAttemptState, setLabAttemptState] = useState(null);
  const [labQuizAnswers, setLabQuizAnswers] = useState({});
  const [labQuizResult, setLabQuizResult] = useState(null);
  const [practiceQuizHistory, setPracticeQuizHistory] = useState({});
  const [flashcardResults, setFlashcardResults] = useState([]);
  const [flashcardIndex, setFlashcardIndex] = useState(0);
  const [flashcardReveal, setFlashcardReveal] = useState(false);
  const [showQR, setShowQR] = useState(false);
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

  const toDateTimeLocalValue = (value) => {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    const offsetMs = dt.getTimezoneOffset() * 60000;
    return new Date(dt.getTime() - offsetMs).toISOString().slice(0, 16);
  };

  const localDateTimeToIso = (value) => {
    if (!value) return null;
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return null;
    return dt.toISOString();
  };

  const quizQuestionCount = (quiz) => {
    const raw = quiz?.question_count;
    if (raw !== undefined && raw !== null && !Number.isNaN(Number(raw))) {
      return Number(raw);
    }
    return (quiz?.questions || []).length;
  };

  const getStudentQuizWindowState = (quiz, currentTime = quizClock) => {
    const startTime = quiz?.scheduled_for ? new Date(quiz.scheduled_for).getTime() : null;
    const endTime = quiz?.due_at ? new Date(quiz.due_at).getTime() : null;
    if (startTime && startTime > currentTime) return "upcoming";
    if (endTime && endTime < currentTime) return "ended";
    return "live";
  };

  const studentQuizStatusLabel = (quiz, currentTime = quizClock) => {
    const state = getStudentQuizWindowState(quiz, currentTime);
    if (state === "upcoming") return "Upcoming";
    if (state === "ended") return "Ended";
    return "Live Now";
  };

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
    if (classworkSelectedModules.length === 0) {
      setClassworkSelectedModules([modules[0].id]);
    }
    if (!classworkQuizSessionId) {
      setClassworkQuizSessionId(modules[0].id);
    }
  }, [courseQuery.data, classworkQuizSessionId, classworkSelectedModules.length, labSelectedModules.length]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setQuizClock(Date.now());
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

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

  const deleteQuiz = useMutation({
    mutationFn: async (quizId) => {
      await client.delete(`/quizzes/${quizId}/`);
      return quizId;
    },
    onSuccess: (quizId) => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      if (activeTeacherQuizId === quizId) {
        setActiveTeacherQuizId(null);
        setTeacherQuizEditMode(false);
      }
      if (activeLiveQuizId === quizId) {
        setActiveLiveQuizId(null);
        setLiveAttemptState(null);
        setLiveQuizAnswers({});
        setLiveQuizResult(null);
      }
      if (labActiveQuizId === quizId) {
        setLabActiveQuizId(null);
        setLabAttemptState(null);
        setLabQuizAnswers({});
        setLabQuizResult(null);
      }
      setPracticeQuizHistory((prev) => {
        const next = { ...prev };
        delete next[quizId];
        return next;
      });
      setLiveQuizSubmissionById((prev) => {
        const next = { ...prev };
        delete next[quizId];
        return next;
      });
    },
  });

  const generateTeacherQuizDraft = useMutation({
    mutationFn: async () => {
      const modules = courseQuery.data?.schedule_items || [];
      const allModuleIds = modules.map((item) => item.id);
      const selectedIds =
        classworkScopeMode === "multiple"
          ? classworkSelectedModules
          : [classworkSelectedModules[0] || classworkQuizSessionId].filter(Boolean);
      const activeIds = selectedIds.length > 0 ? selectedIds : allModuleIds.slice(0, 1);
      const anchorSessionId = activeIds[0] || classworkQuizSessionId || modules[0]?.id;
      if (!anchorSessionId) {
        throw new Error("No module found for quiz generation.");
      }

      return (
        await client.post(`/courses/${courseId}/sessions/${anchorSessionId}/quizzes/generate/`, {
          title: classworkQuizTitle.trim() || undefined,
          instructions: classworkQuizInstructions.trim(),
          question_count: 8,
          scheduled_for: localDateTimeToIso(classworkQuizScheduledFor) || undefined,
          due_at: localDateTimeToIso(classworkQuizDueAt) || undefined,
          shuffle_questions: Boolean(classworkShuffleQuestions),
          shuffle_options: Boolean(classworkShuffleOptions),
          module_scope: classworkScopeMode,
          session_ids: activeIds,
          include_all_modules: false,
        })
      ).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      setActiveTeacherQuizId(null);
      setTeacherQuizEditMode(false);
      setClassworkQuizTitle("");
      setClassworkQuizInstructions("");
      setClassworkQuizScheduledFor("");
      setClassworkQuizDueAt("");
      setClassworkShuffleQuestions(true);
      setClassworkShuffleOptions(true);
    },
  });

  const updateTeacherQuizMeta = useMutation({
    mutationFn: async ({ quizId, payload }) => (await client.patch(`/quizzes/${quizId}/`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      if (activeTeacherQuizId) {
        queryClient.invalidateQueries({ queryKey: ["teacher-quiz-detail", activeTeacherQuizId] });
      }
    },
  });

  const updateTeacherQuizQuestion = useMutation({
    mutationFn: async ({ questionId, payload }) => (await client.patch(`/questions/${questionId}/`, payload)).data,
    onSuccess: () => {
      if (activeTeacherQuizId) {
        queryClient.invalidateQueries({ queryKey: ["teacher-quiz-detail", activeTeacherQuizId] });
      }
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  const createTeacherQuizQuestion = useMutation({
    mutationFn: async ({ quizId, payload }) => (await client.post(`/quizzes/${quizId}/questions/`, payload)).data,
    onSuccess: () => {
      if (activeTeacherQuizId) {
        queryClient.invalidateQueries({ queryKey: ["teacher-quiz-detail", activeTeacherQuizId] });
      }
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      setNewTeacherQuestionDraft(emptyTeacherQuestionDraft());
    },
  });

  const publishTeacherQuiz = useMutation({
    mutationFn: async (quizId) => (await client.post(`/quizzes/${quizId}/publish/`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      if (activeTeacherQuizId) {
        queryClient.invalidateQueries({ queryKey: ["teacher-quiz-detail", activeTeacherQuizId] });
      }
    },
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
          question_count: Number(practiceQuestionCount) || 8,
          module_scope: labScopeMode,
          include_all_modules: false,
          session_ids: activeIds,
          title: practiceQuizName.trim() || `Practice Quiz ${studentPracticeQuizzes.length + 1}`,
        })
      ).data;
    },
    onSuccess: (data) => {
      setLabGeneratedQuizId(data?.id || null);
      setPracticeQuizName("");
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
  const teacherLiveQuizzes = (quizzesQuery.data || []).filter((quiz) => quiz.mode === "LIVE");
  const teacherPublishedQuizzes = teacherLiveQuizzes.filter((quiz) => quiz.state === "PUBLISHED");
  const studentPracticeQuizzes = (quizzesQuery.data || []).filter((quiz) => quiz.mode === "PRACTICE");
  const studentTeacherQuizSections = useMemo(() => {
    const groups = {
      live: [],
      upcoming: [],
      ended: [],
    };

    teacherPublishedQuizzes.forEach((quiz) => {
      groups[getStudentQuizWindowState(quiz)].push(quiz);
    });

    const sortByWindow = (a, b) => {
      const aStart = a.scheduled_for ? new Date(a.scheduled_for).getTime() : 0;
      const bStart = b.scheduled_for ? new Date(b.scheduled_for).getTime() : 0;
      return aStart - bStart;
    };

    return [
      { key: "live", title: "Live Now", quizzes: groups.live.sort(sortByWindow) },
      { key: "upcoming", title: "Upcoming", quizzes: groups.upcoming.sort(sortByWindow) },
      { key: "ended", title: "Ended", quizzes: groups.ended.sort((a, b) => {
        const aEnd = a.due_at ? new Date(a.due_at).getTime() : 0;
        const bEnd = b.due_at ? new Date(b.due_at).getTime() : 0;
        return bEnd - aEnd;
      }) },
    ].filter((group) => group.quizzes.length > 0);
  }, [quizClock, teacherPublishedQuizzes]);
  const selectedStudentLiveQuiz = teacherPublishedQuizzes.find((quiz) => quiz.id === activeLiveQuizId) || null;
  const studentCount = (peopleQuery.data?.students || []).length;
  const materialCount = courseQuery.data?.materials?.length || 0;
  const assignmentCount = assignmentsQuery.data?.length || 0;
  const moduleCount = moduleItems.length;
  const activeInviteCode = peopleQuery.data?.invite_code || courseQuery.data?.invite_code || "------";
  const teacherInitial = (peopleQuery.data?.teacher?.name || user?.name || "T").trim().charAt(0).toUpperCase() || "T";

  const labQuizDetailQuery = useQuery({
    queryKey: ["lab-quiz-detail", labActiveQuizId],
    queryFn: async () => (await client.get(`/quizzes/${labActiveQuizId}/`)).data,
    enabled: isStudent && !!labActiveQuizId,
  });

  const teacherQuizDetailQuery = useQuery({
    queryKey: ["teacher-quiz-detail", activeTeacherQuizId],
    queryFn: async () => (await client.get(`/quizzes/${activeTeacherQuizId}/`)).data,
    enabled: isTeacher && !!activeTeacherQuizId,
  });

  const teacherQuizAnalyticsQuery = useQuery({
    queryKey: ["teacher-quiz-analytics", activeTeacherQuizId],
    queryFn: async () => (await client.get(`/quizzes/${activeTeacherQuizId}/analytics/`)).data,
    enabled: isTeacher && !!activeTeacherQuizId,
  });

  const liveQuizDetailQuery = useQuery({
    queryKey: ["live-quiz-detail", activeLiveQuizId],
    queryFn: async () => (await client.get(`/quizzes/${activeLiveQuizId}/`)).data,
    enabled: isStudent && !!activeLiveQuizId,
  });

  const teacherSelectedQuiz = teacherQuizDetailQuery.data || null;
  const teacherSelectedQuizPublished = teacherSelectedQuiz?.state === "PUBLISHED";

  const startLabAttempt = useMutation({
    mutationFn: async (quizId) => (await client.post(`/quizzes/${quizId}/attempts/start/`, {})).data,
    onSuccess: (data) => {
      const quizId = data?.quiz?.id;
      const previous = quizId ? practiceQuizHistory[quizId] : null;
      setLabAttemptState(data);
      setLabQuizAnswers(previous?.answers || {});
      setLabQuizResult(null);
    },
  });

  const submitLabAttempt = useMutation({
    mutationFn: async () => {
      if (!labAttemptState?.attempt_id) throw new Error("No active attempt.");
      return (await client.post(`/attempts/${labAttemptState.attempt_id}/submit/`, { answers: labQuizAnswers })).data;
    },
    onSuccess: (data) => {
      if (labActiveQuizId) {
        setPracticeQuizHistory((prev) => ({
          ...prev,
          [labActiveQuizId]: {
            result: data,
            answers: { ...labQuizAnswers },
          },
        }));
      }
      setLabQuizResult(data);
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  const startClassworkLiveAttempt = useMutation({
    mutationFn: async (quizId) => (await client.post(`/quizzes/${quizId}/attempts/start/`, {})).data,
    onSuccess: (data) => {
      const isSubmitted = data?.status === "SUBMITTED";
      const resultPayload = isSubmitted
        ? {
            score: data?.score ?? 0,
            max_score: data?.max_score ?? 0,
            percentage: data?.percentage ?? 0,
            results: data?.results || [],
          }
        : null;

      const answerMap = {};
      (resultPayload?.results || []).forEach((item) => {
        answerMap[String(item.question_id)] = item.selected_option_key || "";
      });

      const quizId = data?.quiz?.id;
      if (quizId) {
        setLiveQuizSubmissionById((prev) => ({
          ...prev,
          [quizId]: isSubmitted,
        }));
      }

      setLiveAttemptState(data);
      setLiveQuizAnswers(answerMap);
      setLiveQuizResult(resultPayload);
    },
  });

  const submitClassworkLiveAttempt = useMutation({
    mutationFn: async () => {
      if (!liveAttemptState?.attempt_id) throw new Error("No active live quiz attempt.");
      return (await client.post(`/attempts/${liveAttemptState.attempt_id}/submit/`, { answers: liveQuizAnswers })).data;
    },
    onSuccess: (data) => {
      const answerMap = {};
      (data?.results || []).forEach((item) => {
        answerMap[String(item.question_id)] = item.selected_option_key || "";
      });
      if (activeLiveQuizId) {
        setLiveQuizSubmissionById((prev) => ({
          ...prev,
          [activeLiveQuizId]: true,
        }));
      }
      setLiveAttemptState((prev) => (prev ? { ...prev, status: "SUBMITTED" } : prev));
      setLiveQuizAnswers(answerMap);
      setLiveQuizResult(data);
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

  useEffect(() => {
    if (!isStudent) return;
    if (teacherPublishedQuizzes.length === 0) {
      setActiveLiveQuizId(null);
      setLiveAttemptState(null);
      setLiveQuizAnswers({});
      setLiveQuizResult(null);
      return;
    }

    const quizStillAvailable = teacherPublishedQuizzes.some((quiz) => quiz.id === activeLiveQuizId);
    if (activeLiveQuizId && !quizStillAvailable) {
      setActiveLiveQuizId(null);
      setLiveAttemptState(null);
      setLiveQuizAnswers({});
      setLiveQuizResult(null);
    }
  }, [activeLiveQuizId, isStudent, teacherPublishedQuizzes]);

  useEffect(() => {
    if (!activeLiveQuizId) return;
    setLiveAttemptState(null);
    setLiveQuizAnswers({});
    setLiveQuizResult(null);
  }, [activeLiveQuizId]);

  useEffect(() => {
    if (!isStudent) return;
    const nextMap = {};
    teacherPublishedQuizzes.forEach((quiz) => {
      nextMap[quiz.id] = Boolean(quiz.has_submitted);
    });
    setLiveQuizSubmissionById((prev) => ({ ...prev, ...nextMap }));
  }, [isStudent, teacherPublishedQuizzes]);

  useEffect(() => {
    if (!isTeacher || !activeTeacherQuizId) return;
    const exists = teacherLiveQuizzes.some((quiz) => quiz.id === activeTeacherQuizId);
    if (!exists) {
      setActiveTeacherQuizId(null);
      setTeacherQuizEditMode(false);
    }
  }, [activeTeacherQuizId, isTeacher, teacherLiveQuizzes]);

  useEffect(() => {
    setTeacherQuizEditMode(false);
  }, [activeTeacherQuizId]);

  useEffect(() => {
    const quiz = teacherQuizDetailQuery.data;
    if (!quiz) return;

    setQuizMetaDraft({
      title: quiz.title || "",
      instructions: quiz.instructions || "",
      scheduled_for: toDateTimeLocalValue(quiz.scheduled_for),
      due_at: toDateTimeLocalValue(quiz.due_at),
      shuffle_questions: Boolean(quiz.shuffle_questions ?? true),
      shuffle_options: Boolean(quiz.shuffle_options ?? true),
    });

    const questionDraftMap = {};
    (quiz.questions || []).forEach((question) => {
      questionDraftMap[question.id] = {
        question_text: question.question_text || "",
        difficulty: question.difficulty || "MEDIUM",
        options: (question.options || []).map((option) => ({
          id: option.id,
          option_key: String(option.option_key || "").toUpperCase(),
          option_text: option.option_text || "",
          is_correct: Boolean(option.is_correct),
        })),
      };
    });
    setQuizQuestionDrafts(questionDraftMap);
  }, [teacherQuizDetailQuery.data]);

  useEffect(() => {
    if (!labActiveQuizId) return;
    const latest = labQuizDetailQuery.data?.latest_attempt;
    if (!latest) return;

    const rememberedAnswers = {};
    (latest.results || []).forEach((item) => {
      rememberedAnswers[String(item.question_id)] = item.selected_option_key || "";
    });

    const rememberedResult = {
      score: latest.score,
      max_score: latest.max_score,
      percentage: latest.percentage,
      results: latest.results || [],
    };

    setPracticeQuizHistory((prev) => ({
      ...prev,
      [labActiveQuizId]: {
        result: rememberedResult,
        answers: rememberedAnswers,
      },
    }));

    if (!labAttemptState && !labQuizResult) {
      setLabQuizAnswers(rememberedAnswers);
      setLabQuizResult(rememberedResult);
    }
  }, [labActiveQuizId, labAttemptState, labQuizDetailQuery.data, labQuizResult]);

  const materialViewUrl = (filePath) => {
    if (!filePath) return "";
    if (String(filePath).startsWith("http://") || String(filePath).startsWith("https://")) return filePath;
    const apiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
    const apiOrigin = new URL(apiBase).origin;
    return `${apiOrigin}${filePath}`;
  };

  const materialKind = (url) => {
    const lower = String(url || "").toLowerCase();
    if (lower.endsWith(".pdf")) return "pdf";
    if ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].some((ext) => lower.endsWith(ext))) return "image";
    if ([".mp4", ".webm", ".ogg", ".mov", ".m4v"].some((ext) => lower.endsWith(ext))) return "video";
    if ([".mp3", ".wav", ".m4a", ".aac", ".ogg"].some((ext) => lower.endsWith(ext))) return "audio";
    if ([".txt", ".md"].some((ext) => lower.endsWith(ext))) return "text";
    return "file";
  };

  const toggleMaterialPreview = (materialId) => {
    setMaterialPreviewById((prev) => ({
      ...prev,
      [materialId]: !Boolean(prev[materialId]),
    }));
  };

  const renderMaterialPreview = (material, materialUrl) => {
    const kind = materialKind(materialUrl);
    const textPreview = String(material?.content_text || "").trim();

    if (!materialUrl) {
      return textPreview ? <pre className="material-preview-text">{textPreview.slice(0, 4000)}</pre> : <p className="text-muted">No preview available.</p>;
    }

    if (kind === "pdf" || kind === "file") {
      return (
        <iframe
          src={materialUrl}
          title={`Preview ${material?.title || "material"}`}
          className="material-preview-frame"
        />
      );
    }

    if (kind === "image") {
      return <img src={materialUrl} alt={material?.title || "Material preview"} className="material-preview-image" />;
    }

    if (kind === "video") {
      return <video src={materialUrl} controls className="material-preview-video" />;
    }

    if (kind === "audio") {
      return <audio src={materialUrl} controls className="material-preview-audio" />;
    }

    return textPreview ? <pre className="material-preview-text">{textPreview.slice(0, 4000)}</pre> : <p className="text-muted">No preview available.</p>;
  };

  const updateQuizDraftQuestion = (questionId, updater) => {
    setQuizQuestionDrafts((prev) => {
      const current = prev[questionId] || { question_text: "", difficulty: "MEDIUM", options: [] };
      const next = typeof updater === "function" ? updater(current) : { ...current, ...updater };
      return { ...prev, [questionId]: next };
    });
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

  const toggleClassworkModule = (moduleId) => {
    setClassworkSelectedModules((prev) => {
      const next = prev.includes(moduleId)
        ? prev.filter((id) => id !== moduleId)
        : [...prev, moduleId];
      const resolved = next.length > 0 ? next : [moduleId];
      setClassworkQuizSessionId(resolved[0] || null);
      return resolved;
    });
  };

  const clearActiveLiveQuizView = () => {
    setActiveLiveQuizId(null);
    setLiveAttemptState(null);
    setLiveQuizAnswers({});
    setLiveQuizResult(null);
  };

  const summarizeQuizResult = (result) => {
    const rows = result?.results || [];
    const total = rows.length;
    const answered = rows.filter((item) => Boolean(item.selected_option_key)).length;
    const correct = rows.filter((item) => Boolean(item.is_correct)).length;
    return {
      total,
      answered,
      correct,
      wrong: Math.max(answered - correct, 0),
      unanswered: Math.max(total - answered, 0),
    };
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
        <section className="panel hero compact classroom-hero">
          <div className="classroom-hero-main">
            <div className="classroom-hero-copy">
              <p className="eyebrow">My Classroom</p>
              <h2>{courseQuery.data?.name || "AI Learning Space"}</h2>
              <p className="classroom-hero-description">
                {courseQuery.data?.description || "A focused classroom hub for materials, assignments, quizzes, and AI-supported learning."}
              </p>
            </div>
            <div className="classroom-hero-actions">
              <div className="classroom-hero-code">
                <span className="classroom-hero-code-label">Invite Code</span>
                <strong>{activeInviteCode}</strong>
              </div>
              {isTeacher && (
                <button
                  className="btn-secondary text-danger classroom-danger-btn"
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
            </div>
          </div>
          <div className="classroom-hero-stats">
            <div className="classroom-stat-card">
              <span>Students</span>
              <strong>{studentCount}</strong>
            </div>
            <div className="classroom-stat-card">
              <span>Materials</span>
              <strong>{materialCount}</strong>
            </div>
            <div className="classroom-stat-card">
              <span>Modules</span>
              <strong>{moduleCount}</strong>
            </div>
            <div className="classroom-stat-card">
              <span>Assignments</span>
              <strong>{assignmentCount}</strong>
            </div>
          </div>
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
            <div className="stream-top-grid">
              <div className="panel compact stream-code-panel">
                <p className="eyebrow">Classroom Code</p>
                <h3 className="stream-code-value">{activeInviteCode}</h3>
                <p className="text-muted">Share this code with students so they can join the classroom instantly.</p>
                <div className="actions">
                  <button className="btn-secondary" onClick={() => navigator.clipboard.writeText(activeInviteCode)}>Copy Code</button>
                  {isTeacher && (
                    <button className="btn-secondary" onClick={() => rotateInviteCode.mutate()} disabled={rotateInviteCode.isPending}>
                      {rotateInviteCode.isPending ? "Rotating..." : "Rotate Code"}
                    </button>
                  )}
                  {isTeacher && (
                    <button className="btn-secondary" onClick={() => setShowQR(!showQR)}>
                      {showQR ? "Hide QR" : "Show QR Code"}
                    </button>
                  )}
                </div>
                {isTeacher && showQR && (
                  <div style={{ marginTop: '1rem', textAlign: 'center', background: '#fff', padding: '1rem', borderRadius: '8px' }}>
                    <img 
                      src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(activeInviteCode)}`} 
                      alt={`QR for ${activeInviteCode}`} 
                    />
                  </div>
                )}
              </div>
            </div>

            {hasMaterials && (
              <div className="stream-material-grid">
                {courseQuery.data.materials.map((mat) => {
                  const materialUrl = materialViewUrl(mat.file);
                  const typeLabel = materialKind(materialUrl).toUpperCase();
                  const isPreviewOpen = Boolean(materialPreviewById[mat.id]);

                  return (
                    <article key={mat.id} className="stream-material-card">
                      <div className="stream-material-main">
                        <div className="stream-material-topline">
                          <span className="stream-material-type">{typeLabel}</span>
                          {isTeacher && (
                            <span className={`chip status-${mat.parse_status?.toLowerCase() || "pending"}`}>
                              {mat.parse_status || "Parsed"}
                            </span>
                          )}
                        </div>
                        <strong>{mat.title}</strong>
                        <p className="text-muted">
                          {materialUrl
                            ? "Ready for preview, download, and AI retrieval."
                            : "Saved as a text-only classroom resource."}
                        </p>
                      </div>
                      <div className="stream-material-actions">
                        <button className="btn-secondary" onClick={() => toggleMaterialPreview(mat.id)}>
                          {isPreviewOpen ? "Hide Preview" : "Show Preview"}
                        </button>
                        {materialUrl ? (
                          <>
                            <a className="btn-secondary" href={materialUrl} target="_blank" rel="noreferrer">Open</a>
                            <a className="btn-secondary" href={materialUrl} download>Download</a>
                          </>
                        ) : (
                          <span className="chip">TEXT</span>
                        )}
                        {isTeacher && (
                          <button
                            className="btn-secondary text-danger"
                            title="Delete Material"
                            onClick={() => {
                              if (window.confirm(`Remove "${mat.title}"?`)) {
                                deleteMaterial.mutate(mat.id);
                              }
                            }}
                            disabled={deleteMaterial.isPending && deleteMaterial.variables === mat.id}
                          >
                            {deleteMaterial.isPending && deleteMaterial.variables === mat.id ? "Removing..." : "Delete"}
                          </button>
                        )}
                      </div>
                      {isPreviewOpen && (
                        <div className="stream-material-preview">
                          {renderMaterialPreview(mat, materialUrl)}
                        </div>
                      )}
                    </article>
                  );
                })}
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
                    const typeLabel = materialKind(materialUrl).toUpperCase();
                    const isPreviewOpen = Boolean(materialPreviewById[mat.id]);
                    return (
                      <div key={mat.id} className="material-card stack compact" style={{ alignItems: "stretch" }}>
                        <div className="material-info">
                          <strong>{mat.title}</strong>
                          <span className="chip">{typeLabel}</span>
                          {isTeacher && (
                            <span className={`chip status-${mat.parse_status?.toLowerCase() || "pending"}`}>
                              {mat.parse_status || "Parsed"}
                            </span>
                          )}
                        </div>
                        <div className="actions">
                          <button className="btn-secondary" onClick={() => toggleMaterialPreview(mat.id)}>
                            {isPreviewOpen ? "Hide Preview" : "Show Preview"}
                          </button>
                          {materialUrl ? (
                            <>
                              <a className="btn-secondary" href={materialUrl} target="_blank" rel="noreferrer">View File</a>
                              <a className="btn-secondary" href={materialUrl} download>Download</a>
                            </>
                          ) : (
                            <span className="text-muted">Text-only material</span>
                          )}
                        </div>
                        {isPreviewOpen && (
                          <div className="material-preview-wrap">
                            {renderMaterialPreview(mat, materialUrl)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {isTeacher && (
              <section className="panel stack compact">
                <div className="section-header">
                  <h3>Teacher Quizzes</h3>
                  <span className="chip">{teacherLiveQuizzes.length} total</span>
                </div>

                <div className="quiz-create-bar">
                  <div className="quiz-create-head">
                    <strong>Create Quiz Draft</strong>
                    <p className="text-muted">Generate an AI draft, review questions, then publish when ready.</p>
                  </div>

                  <div className="actions" style={{ marginTop: 0 }}>
                    <button
                      className={`btn-secondary ${classworkScopeMode === "single" ? "active-scope" : ""}`}
                      onClick={() => {
                        setClassworkScopeMode("single");
                        if (classworkSelectedModules.length > 1) {
                          const first = classworkSelectedModules[0];
                          setClassworkSelectedModules([first]);
                          setClassworkQuizSessionId(first);
                        }
                        if (classworkSelectedModules.length === 0 && moduleItems.length > 0) {
                          const fallback = moduleItems[0].id;
                          setClassworkSelectedModules([fallback]);
                          setClassworkQuizSessionId(fallback);
                        }
                      }}
                    >
                      Single Module
                    </button>
                    <button
                      className={`btn-secondary ${classworkScopeMode === "multiple" ? "active-scope" : ""}`}
                      onClick={() => {
                        setClassworkScopeMode("multiple");
                        if (classworkSelectedModules.length === 0 && moduleItems.length > 0) {
                          const fallback = moduleItems[0].id;
                          setClassworkSelectedModules([fallback]);
                          setClassworkQuizSessionId(fallback);
                        }
                      }}
                    >
                      Multiple Modules
                    </button>
                  </div>

                  <div className="quiz-create-controls">
                    <label className="quiz-field">
                      <span>Title</span>
                      <input
                        className="input-field"
                        value={classworkQuizTitle}
                        onChange={(e) => setClassworkQuizTitle(e.target.value)}
                        placeholder="Quiz title (optional)"
                      />
                    </label>
                    <label className="quiz-field">
                      <span>Start Time</span>
                      <input
                        className="input-field"
                        type="datetime-local"
                        value={classworkQuizScheduledFor}
                        onChange={(e) => setClassworkQuizScheduledFor(e.target.value)}
                        title="Scheduled start (optional)"
                      />
                    </label>
                    <label className="quiz-field">
                      <span>End Time</span>
                      <input
                        className="input-field"
                        type="datetime-local"
                        value={classworkQuizDueAt}
                        onChange={(e) => setClassworkQuizDueAt(e.target.value)}
                        title="Due time (optional)"
                      />
                    </label>
                  </div>

                  {classworkScopeMode === "single" ? (
                    <label className="quiz-field">
                      <span>Module</span>
                      <select
                        value={classworkSelectedModules[0] || classworkQuizSessionId || ""}
                        onChange={(e) => {
                          const moduleId = Number(e.target.value);
                          setClassworkSelectedModules([moduleId]);
                          setClassworkQuizSessionId(moduleId);
                        }}
                      >
                        {moduleItems.map((item) => (
                          <option key={item.id} value={item.id}>
                            Class {item.class_number}: {item.topic}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <div className="stack compact">
                      <div className="actions" style={{ marginTop: 0 }}>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            const allIds = moduleItems.map((item) => item.id);
                            if (classworkSelectedModules.length === allIds.length) {
                              const fallback = allIds.slice(0, 1);
                              setClassworkSelectedModules(fallback);
                              setClassworkQuizSessionId(fallback[0] || null);
                            } else {
                              setClassworkSelectedModules(allIds);
                              setClassworkQuizSessionId(allIds[0] || null);
                            }
                          }}
                        >
                          {classworkSelectedModules.length === moduleItems.length ? "Clear All" : "Select All"}
                        </button>
                      </div>
                      {moduleItems.map((item) => (
                        <label key={item.id} className="option-label">
                          <input
                            type="checkbox"
                            checked={classworkSelectedModules.includes(item.id)}
                            onChange={() => toggleClassworkModule(item.id)}
                          />
                          Class {item.class_number}: {item.topic}
                        </label>
                      ))}
                    </div>
                  )}

                  <div className="quiz-toggle-row">
                    <label className="quiz-toggle-item">
                      <input
                        type="checkbox"
                        checked={classworkShuffleQuestions}
                        onChange={(e) => setClassworkShuffleQuestions(e.target.checked)}
                      />
                      Random question order per student
                    </label>
                    <label className="quiz-toggle-item">
                      <input
                        type="checkbox"
                        checked={classworkShuffleOptions}
                        onChange={(e) => setClassworkShuffleOptions(e.target.checked)}
                      />
                      Random option order per student
                    </label>
                  </div>

                  <label className="quiz-field quiz-field-full">
                    <span>Instructions</span>
                    <textarea
                      className="input-field"
                      rows="3"
                      value={classworkQuizInstructions}
                      onChange={(e) => setClassworkQuizInstructions(e.target.value)}
                      placeholder="Instructions for students (optional)"
                    />
                  </label>

                  <div className="quiz-create-footer">
                    <span className="text-muted text-small">You can edit questions before publishing.</span>
                    <button
                      className="btn-primary"
                      onClick={() => generateTeacherQuizDraft.mutate()}
                      disabled={generateTeacherQuizDraft.isPending || moduleItems.length === 0}
                    >
                      {generateTeacherQuizDraft.isPending ? "Generating Quiz Draft..." : "Create Quiz Draft (AI)"}
                    </button>
                  </div>
                </div>

                {teacherLiveQuizzes.length === 0 ? (
                  <p className="empty-state">No quizzes yet. Generate your first AI draft.</p>
                ) : (
                  <div className="quiz-list-simple">
                    {teacherLiveQuizzes.map((quiz) => {
                      const isActiveQuiz = activeTeacherQuizId === quiz.id;
                      const isEditingThisQuiz = isActiveQuiz && teacherQuizEditMode;
                      return (
                        <div key={quiz.id} className={`quiz-list-row ${isActiveQuiz ? "is-active" : ""}`}>
                          <div className="quiz-list-meta">
                          <strong>{quiz.title}</strong>
                          <span className={`chip status-${String(quiz.state || "REVIEW").toLowerCase()}`}>{quiz.state}</span>
                          <span className="chip">{quizQuestionCount(quiz)} questions</span>
                          <span className="text-muted text-small">Session #{quiz.session}</span>
                          {quiz.scheduled_for && <span className="chip">Scheduled</span>}
                        </div>
                          <div className="actions quiz-row-actions">
                            <button
                              className="btn-secondary"
                              onClick={() => {
                                if (isActiveQuiz && !isEditingThisQuiz) {
                                  setActiveTeacherQuizId(null);
                                  setTeacherQuizEditMode(false);
                                  return;
                                }
                                setActiveTeacherQuizId(quiz.id);
                                setTeacherQuizEditMode(false);
                              }}
                            >
                              {isActiveQuiz && !isEditingThisQuiz ? "Hide" : "View"}
                            </button>
                            {quiz.state !== "PUBLISHED" && (
                              <button
                                className="btn-secondary"
                                onClick={() => {
                                  if (isEditingThisQuiz) {
                                    setTeacherQuizEditMode(false);
                                    return;
                                  }
                                  setActiveTeacherQuizId(quiz.id);
                                  setTeacherQuizEditMode(true);
                                }}
                              >
                                {isEditingThisQuiz ? "Stop Editing" : "Edit"}
                              </button>
                            )}
                            {quiz.state !== "PUBLISHED" && (
                              <button
                                className="btn-primary"
                                onClick={() => publishTeacherQuiz.mutate(quiz.id)}
                                disabled={publishTeacherQuiz.isPending}
                              >
                                {publishTeacherQuiz.isPending ? "Publishing..." : "Publish"}
                              </button>
                            )}
                            <button
                              className="btn-secondary text-danger"
                              onClick={() => {
                                if (window.confirm(`Delete quiz "${quiz.title}"? This cannot be undone.`)) {
                                  deleteQuiz.mutate(quiz.id);
                                }
                              }}
                              disabled={deleteQuiz.isPending}
                            >
                              {deleteQuiz.isPending ? "Deleting..." : "Delete"}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeTeacherQuizId && teacherSelectedQuiz && (
                  <div className="quiz-detail-simple">
                    <div className="section-header">
                      <h4>{teacherSelectedQuiz.title || "Quiz"}</h4>
                      <span className={`chip status-${String(teacherSelectedQuiz.state || "REVIEW").toLowerCase()}`}>
                        {teacherSelectedQuiz.state}
                      </span>
                    </div>
                    {(teacherSelectedQuiz.scheduled_for || teacherSelectedQuiz.due_at) && (
                      <p className="text-muted text-small">
                        {teacherSelectedQuiz.scheduled_for ? `Starts: ${new Date(teacherSelectedQuiz.scheduled_for).toLocaleString()}` : ""}
                        {teacherSelectedQuiz.scheduled_for && teacherSelectedQuiz.due_at ? " | " : ""}
                        {teacherSelectedQuiz.due_at ? `Ends: ${new Date(teacherSelectedQuiz.due_at).toLocaleString()}` : ""}
                      </p>
                    )}

                    {teacherSelectedQuizPublished ? (
                      <p className="text-muted">Published quiz is read-only. Students can now attempt it.</p>
                    ) : (
                      <div className="actions quiz-detail-actions" style={{ marginTop: 0 }}>
                        <button
                          className="btn-secondary"
                          onClick={() => setTeacherQuizEditMode((prev) => !prev)}
                        >
                          {teacherQuizEditMode ? "View Questions" : "Edit Questions"}
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            updateTeacherQuizMeta.mutate({
                              quizId: activeTeacherQuizId,
                              payload: {
                                title: quizMetaDraft.title,
                                instructions: quizMetaDraft.instructions,
                                scheduled_for: localDateTimeToIso(quizMetaDraft.scheduled_for),
                                due_at: localDateTimeToIso(quizMetaDraft.due_at),
                                shuffle_questions: Boolean(quizMetaDraft.shuffle_questions),
                                shuffle_options: Boolean(quizMetaDraft.shuffle_options),
                              },
                            });
                          }}
                          disabled={!teacherQuizEditMode || updateTeacherQuizMeta.isPending}
                        >
                          {updateTeacherQuizMeta.isPending ? "Saving Quiz..." : "Save Quiz Details"}
                        </button>
                        <button
                          className="btn-primary"
                          onClick={() => publishTeacherQuiz.mutate(activeTeacherQuizId)}
                          disabled={publishTeacherQuiz.isPending}
                        >
                          {publishTeacherQuiz.isPending ? "Publishing..." : "Publish Quiz"}
                        </button>
                      </div>
                    )}

                    {teacherQuizEditMode && !teacherSelectedQuizPublished && (
                      <div className="quiz-edit-shell">
                        <input
                          className="input-field"
                          value={quizMetaDraft.title || ""}
                          onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, title: e.target.value }))}
                          placeholder="Quiz title"
                        />
                        <textarea
                          className="input-field"
                          rows="3"
                          value={quizMetaDraft.instructions || ""}
                          onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, instructions: e.target.value }))}
                          placeholder="Quiz instructions"
                        />
                        <div className="quiz-edit-grid">
                          <input
                            className="input-field"
                            type="datetime-local"
                            value={quizMetaDraft.scheduled_for || ""}
                            onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, scheduled_for: e.target.value }))}
                            title="Scheduled start (optional)"
                          />
                          <input
                            className="input-field"
                            type="datetime-local"
                            value={quizMetaDraft.due_at || ""}
                            onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, due_at: e.target.value }))}
                            title="Due time (optional)"
                          />
                        </div>
                        <div className="quiz-toggle-row">
                          <label className="quiz-toggle-item">
                            <input
                              type="checkbox"
                              checked={Boolean(quizMetaDraft.shuffle_questions)}
                              onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, shuffle_questions: e.target.checked }))}
                            />
                            Random question order per student
                          </label>
                          <label className="quiz-toggle-item">
                            <input
                              type="checkbox"
                              checked={Boolean(quizMetaDraft.shuffle_options)}
                              onChange={(e) => setQuizMetaDraft((prev) => ({ ...prev, shuffle_options: e.target.checked }))}
                            />
                            Random option order per student
                          </label>
                        </div>
                        <div className="quiz-add-question-shell">
                          <h5>Add Question</h5>
                          <textarea
                            className="input-field"
                            rows="2"
                            value={newTeacherQuestionDraft.question_text}
                            onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, question_text: e.target.value }))}
                            placeholder="Question text"
                          />
                          <div className="quiz-edit-grid">
                            <input
                              className="input-field"
                              value={newTeacherQuestionDraft.option_a}
                              onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, option_a: e.target.value }))}
                              placeholder="Option A"
                            />
                            <input
                              className="input-field"
                              value={newTeacherQuestionDraft.option_b}
                              onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, option_b: e.target.value }))}
                              placeholder="Option B"
                            />
                            <input
                              className="input-field"
                              value={newTeacherQuestionDraft.option_c}
                              onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, option_c: e.target.value }))}
                              placeholder="Option C"
                            />
                            <input
                              className="input-field"
                              value={newTeacherQuestionDraft.option_d}
                              onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, option_d: e.target.value }))}
                              placeholder="Option D"
                            />
                          </div>
                          <div className="quiz-edit-grid">
                            <label className="quiz-field">
                              <span>Correct Option</span>
                              <select
                                value={newTeacherQuestionDraft.correct_option_key}
                                onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, correct_option_key: e.target.value }))}
                              >
                                {["A", "B", "C", "D"].map((key) => (
                                  <option key={key} value={key}>
                                    {key}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="quiz-field">
                              <span>Difficulty</span>
                              <select
                                value={newTeacherQuestionDraft.difficulty}
                                onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, difficulty: e.target.value }))}
                              >
                                <option value="EASY">Easy</option>
                                <option value="MEDIUM">Medium</option>
                                <option value="HARD">Hard</option>
                              </select>
                            </label>
                          </div>
                          <textarea
                            className="input-field"
                            rows="2"
                            value={newTeacherQuestionDraft.explanation}
                            onChange={(e) => setNewTeacherQuestionDraft((prev) => ({ ...prev, explanation: e.target.value }))}
                            placeholder="Explanation (optional)"
                          />
                          <div className="actions" style={{ marginTop: 0 }}>
                            <button
                              className="btn-secondary"
                              onClick={() => setNewTeacherQuestionDraft(emptyTeacherQuestionDraft())}
                              disabled={createTeacherQuizQuestion.isPending}
                            >
                              Reset
                            </button>
                            <button
                              className="btn-primary"
                              onClick={() => {
                                const questionText = String(newTeacherQuestionDraft.question_text || "").trim();
                                if (!questionText) {
                                  window.alert("Question text is required.");
                                  return;
                                }

                                const options = [
                                  { option_key: "A", option_text: String(newTeacherQuestionDraft.option_a || "").trim() },
                                  { option_key: "B", option_text: String(newTeacherQuestionDraft.option_b || "").trim() },
                                  { option_key: "C", option_text: String(newTeacherQuestionDraft.option_c || "").trim() },
                                  { option_key: "D", option_text: String(newTeacherQuestionDraft.option_d || "").trim() },
                                ];
                                if (options.some((option) => !option.option_text)) {
                                  window.alert("Please fill all options A, B, C, and D.");
                                  return;
                                }

                                createTeacherQuizQuestion.mutate({
                                  quizId: activeTeacherQuizId,
                                  payload: {
                                    question_text: questionText,
                                    difficulty: newTeacherQuestionDraft.difficulty || "MEDIUM",
                                    explanation: String(newTeacherQuestionDraft.explanation || "").trim(),
                                    options: options.map((option) => ({
                                      ...option,
                                      is_correct: option.option_key === newTeacherQuestionDraft.correct_option_key,
                                    })),
                                  },
                                });
                              }}
                              disabled={createTeacherQuizQuestion.isPending}
                            >
                              {createTeacherQuizQuestion.isPending ? "Adding..." : "Add Question"}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="quiz-analytics-shell">
                      <div className="section-header">
                        <h5>Student Submissions</h5>
                        <button
                          className="btn-secondary"
                          onClick={() => teacherQuizAnalyticsQuery.refetch()}
                          disabled={teacherQuizAnalyticsQuery.isFetching}
                        >
                          {teacherQuizAnalyticsQuery.isFetching ? "Refreshing..." : "Refresh Scores"}
                        </button>
                      </div>
                      {teacherQuizAnalyticsQuery.isLoading ? (
                        <p className="text-muted">Loading submissions...</p>
                      ) : teacherQuizAnalyticsQuery.data ? (
                        <>
                          <div className="quiz-analytics-summary">
                            <div className="quiz-analytics-card">
                              <span>Submitted</span>
                              <strong>{teacherQuizAnalyticsQuery.data.attempt_count ?? 0}</strong>
                            </div>
                            <div className="quiz-analytics-card">
                              <span>Class Average</span>
                              <strong>{teacherQuizAnalyticsQuery.data.average_percentage ?? 0}%</strong>
                            </div>
                            <div className="quiz-analytics-card">
                              <span>Low-Score Threshold</span>
                              <strong>{teacherQuizAnalyticsQuery.data.threshold ?? 60}%</strong>
                            </div>
                          </div>
                          {(teacherQuizAnalyticsQuery.data.students || []).length > 0 ? (
                            <div className="quiz-attempt-list">
                              {(teacherQuizAnalyticsQuery.data.students || []).map((studentRow) => (
                                <div key={`${studentRow.student_id}-${studentRow.submitted_at || "none"}`} className="quiz-attempt-row">
                                  <div>
                                    <strong>{studentRow.student_name || `Student ${studentRow.student_id}`}</strong>
                                    <p className="text-muted text-small">
                                      Submitted: {studentRow.submitted_at ? new Date(studentRow.submitted_at).toLocaleString() : "N/A"}
                                    </p>
                                  </div>
                                  <div className="quiz-attempt-score">
                                    <strong>{studentRow.percentage}%</strong>
                                    <span className="text-muted text-small">{studentRow.score} / {studentRow.max_score}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-muted">No students have submitted this quiz yet.</p>
                          )}
                        </>
                      ) : (
                        <p className="text-muted">No analytics available right now.</p>
                      )}
                    </div>

                    <div className="quiz-question-list">
                      {(teacherSelectedQuiz.questions || []).length === 0 ? (
                        <p className="text-muted">
                          No questions yet. {teacherQuizEditMode && !teacherSelectedQuizPublished ? "Use Add Question above." : "Switch to edit mode to add one."}
                        </p>
                      ) : (teacherSelectedQuiz.questions || []).map((question) => {
                        const draft = quizQuestionDrafts[question.id] || {
                          question_text: question.question_text || "",
                          difficulty: question.difficulty || "MEDIUM",
                          options: question.options || [],
                        };

                        const optionOrder = { A: 1, B: 2, C: 3, D: 4 };
                        const orderedOptions = [...(draft.options || [])].sort(
                          (a, b) => (optionOrder[String(a.option_key || "").toUpperCase()] || 99) - (optionOrder[String(b.option_key || "").toUpperCase()] || 99)
                        );

                        if (!teacherQuizEditMode || teacherSelectedQuizPublished) {
                          return (
                            <div key={question.id} className="quiz-question-simple">
                              <strong>Q{question.order_index}: {question.question_text}</strong>
                              <ul className="quiz-option-list">
                                {(question.options || []).map((option) => (
                                  <li key={`${question.id}-${option.id || option.option_key}`}>
                                    <span>{String(option.option_key || "").toUpperCase()}. {option.option_text}</span>
                                    {option.is_correct && <span className="chip">Correct</span>}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          );
                        }

                        return (
                          <div key={question.id} className="quiz-question-simple">
                            <textarea
                              className="input-field"
                              rows="2"
                              value={draft.question_text || ""}
                              onChange={(e) => {
                                const nextText = e.target.value;
                                updateQuizDraftQuestion(question.id, (current) => ({
                                  ...current,
                                  question_text: nextText,
                                }));
                              }}
                            />
                            <div className="stack compact">
                              {orderedOptions.map((option) => (
                                <label key={`${question.id}-${option.option_key}`} className="option-label" style={{ alignItems: "center", gap: "0.6rem" }}>
                                  <input
                                    type="radio"
                                    name={`correct_${question.id}`}
                                    checked={Boolean(option.is_correct)}
                                    onChange={() => {
                                      updateQuizDraftQuestion(question.id, (current) => ({
                                        ...current,
                                        options: (current.options || []).map((item) => ({
                                          ...item,
                                          is_correct: String(item.option_key || "").toUpperCase() === String(option.option_key || "").toUpperCase(),
                                        })),
                                      }));
                                    }}
                                  />
                                  <span style={{ minWidth: "1.2rem" }}>{String(option.option_key || "").toUpperCase()}.</span>
                                  <input
                                    className="input-field"
                                    value={option.option_text || ""}
                                    onChange={(e) => {
                                      const nextText = e.target.value;
                                      updateQuizDraftQuestion(question.id, (current) => ({
                                        ...current,
                                        options: (current.options || []).map((item) => {
                                          const itemKey = String(item.option_key || "").toUpperCase();
                                          const targetKey = String(option.option_key || "").toUpperCase();
                                          if (itemKey !== targetKey) return item;
                                          return { ...item, option_text: nextText };
                                        }),
                                      }));
                                    }}
                                  />
                                </label>
                              ))}
                            </div>
                            <button
                              className="btn-secondary"
                              onClick={() => {
                                const current = quizQuestionDrafts[question.id] || draft;
                                const questionText = String(current.question_text || "").trim();
                                if (!questionText) {
                                  window.alert("Question text cannot be empty.");
                                  return;
                                }
                                const optionsByKey = new Map(
                                  (current.options || []).map((item) => [String(item.option_key || "").toUpperCase(), item])
                                );
                                const normalizedOptions = ["A", "B", "C", "D"].map((key) => {
                                  const source = optionsByKey.get(key);
                                  return {
                                    option_key: key,
                                    option_text: String(source?.option_text || "").trim(),
                                    is_correct: Boolean(source?.is_correct),
                                  };
                                });

                                if (normalizedOptions.some((item) => !item.option_text)) {
                                  window.alert("Each option A-D needs text before saving.");
                                  return;
                                }

                                const correctCount = normalizedOptions.filter((item) => item.is_correct).length;
                                if (correctCount !== 1) {
                                  window.alert("Select exactly one correct option.");
                                  return;
                                }

                                updateTeacherQuizQuestion.mutate({
                                  questionId: question.id,
                                  payload: {
                                    question_text: questionText,
                                    difficulty: current.difficulty || "MEDIUM",
                                    options: normalizedOptions,
                                  },
                                });
                              }}
                              disabled={updateTeacherQuizQuestion.isPending}
                            >
                              {updateTeacherQuizQuestion.isPending ? "Saving Question..." : "Save Question"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {!activeTeacherQuizId && teacherLiveQuizzes.length > 0 && (
                  <p className="text-muted">Click View on a quiz row to see questions.</p>
                )}
              </section>
            )}

            {isStudent && (
              <section className="panel stack compact">
                <div className="section-header">
                  <h3>Teacher Quizzes</h3>
                  <span className="chip">{teacherPublishedQuizzes.length} published</span>
                </div>
                {teacherPublishedQuizzes.length === 0 ? (
                  <p className="empty-state">No teacher quiz has been published yet.</p>
                ) : (
                  <div className="quiz-status-board">
                    {studentTeacherQuizSections.map((group) => (
                      <div key={group.key} className="quiz-status-group">
                        <div className="quiz-status-heading">
                          <h4>{group.title}</h4>
                          <span className="chip">{group.quizzes.length}</span>
                        </div>
                        <div className="quiz-list-simple">
                          {group.quizzes.map((quiz) => {
                            const hasSubmitted = Boolean(liveQuizSubmissionById[quiz.id]);
                            const quizWindowState = getStudentQuizWindowState(quiz);
                            const isInProgress = activeLiveQuizId === quiz.id && liveAttemptState?.status === "IN_PROGRESS" && !hasSubmitted;
                            const isLoadingThisQuiz = startClassworkLiveAttempt.isPending && startClassworkLiveAttempt.variables === quiz.id;
                            const isScoreOpen = hasSubmitted && activeLiveQuizId === quiz.id && Boolean(liveQuizResult);
                            const isCardActive = activeLiveQuizId === quiz.id && (Boolean(liveQuizResult) || Boolean(liveAttemptState));
                            const scheduleLine = [
                              quiz.scheduled_for ? `Starts: ${new Date(quiz.scheduled_for).toLocaleString()}` : "Starts immediately",
                              quiz.due_at ? `Ends: ${new Date(quiz.due_at).toLocaleString()}` : "No end time",
                            ].join(" | ");
                            return (
                              <div
                                key={quiz.id}
                                className={`quiz-student-card is-${quizWindowState} ${isCardActive ? "is-active" : ""}`}
                              >
                                <div className="quiz-student-header">
                                  <div className="quiz-student-title">
                                    <strong>{quiz.title}</strong>
                                    <p className="text-muted text-small">
                                      {quiz.instructions?.trim() || "Review the timing below and start when the quiz window is open."}
                                    </p>
                                  </div>
                                  <span className={`chip quiz-window-chip quiz-window-chip-${quizWindowState}`}>
                                    {studentQuizStatusLabel(quiz)}
                                  </span>
                                </div>
                                <div className="quiz-student-meta">
                                  <span className="chip">{quizQuestionCount(quiz)} questions</span>
                                  {quiz.time_limit_minutes ? <span className="chip">{quiz.time_limit_minutes} min limit</span> : null}
                                  {hasSubmitted ? <span className="chip status-success">Submitted</span> : null}
                                </div>
                                <div className="quiz-student-timing">
                                  <span>{scheduleLine}</span>
                                </div>
                                <div className="actions quiz-row-actions quiz-student-actions" style={{ marginTop: 0 }}>
                                  {hasSubmitted ? (
                                    <button
                                      className="btn-secondary"
                                      onClick={() => {
                                        if (isScoreOpen) {
                                          clearActiveLiveQuizView();
                                          return;
                                        }
                                        setActiveLiveQuizId(quiz.id);
                                        startClassworkLiveAttempt.mutate(quiz.id);
                                      }}
                                      disabled={startClassworkLiveAttempt.isPending && !isScoreOpen}
                                    >
                                      {isScoreOpen ? "Hide Score" : isLoadingThisQuiz ? "Loading..." : "View Score"}
                                    </button>
                                  ) : quizWindowState === "upcoming" ? (
                                    <button className="btn-secondary" disabled>
                                      Upcoming
                                    </button>
                                  ) : quizWindowState === "ended" ? (
                                    <button className="btn-secondary" disabled>
                                      Ended
                                    </button>
                                  ) : (
                                    <button
                                      className="btn-primary"
                                      onClick={() => {
                                        setActiveLiveQuizId(quiz.id);
                                        startClassworkLiveAttempt.mutate(quiz.id);
                                      }}
                                      disabled={startClassworkLiveAttempt.isPending}
                                    >
                                      {isLoadingThisQuiz ? "Loading..." : isInProgress ? "Resume Quiz" : "Start Quiz"}
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {activeLiveQuizId && (liveAttemptState || liveQuizResult || (startClassworkLiveAttempt.isPending && startClassworkLiveAttempt.variables === activeLiveQuizId)) && (
                  <div className="quiz-detail-simple student-quiz-detail">
                    <div className="quiz-student-detail-top">
                      <div>
                        <p className="eyebrow">Active Quiz</p>
                        <h4>{liveQuizDetailQuery.data?.title || selectedStudentLiveQuiz?.title || "Live Quiz"}</h4>
                        <p className="text-muted text-small">
                          {selectedStudentLiveQuiz?.instructions?.trim() || "Answer the questions below and submit when you are ready."}
                        </p>
                      </div>
                      <div className="quiz-student-detail-meta">
                        <span className="chip">{quizQuestionCount(liveQuizDetailQuery.data || selectedStudentLiveQuiz)} questions</span>
                        {selectedStudentLiveQuiz ? (
                          <span className={`chip quiz-window-chip quiz-window-chip-${getStudentQuizWindowState(selectedStudentLiveQuiz)}`}>
                            {studentQuizStatusLabel(selectedStudentLiveQuiz)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {selectedStudentLiveQuiz && (
                      <div className="quiz-student-timing detail-timing">
                        <span>
                          {selectedStudentLiveQuiz.scheduled_for ? `Starts: ${new Date(selectedStudentLiveQuiz.scheduled_for).toLocaleString()}` : "Starts immediately"}
                          {" | "}
                          {selectedStudentLiveQuiz.due_at ? `Ends: ${new Date(selectedStudentLiveQuiz.due_at).toLocaleString()}` : "No end time"}
                        </span>
                      </div>
                    )}
                    <div className="section-header">
                      <h4>{liveQuizResult ? "Submission Review" : "Questions"}</h4>
                      {liveAttemptState?.status === "IN_PROGRESS" ? (
                        <span className="chip">
                          {Object.values(liveQuizAnswers).filter(Boolean).length}/{quizQuestionCount(liveQuizDetailQuery.data || liveAttemptState?.quiz)} answered
                        </span>
                      ) : null}
                    </div>

                    {!liveAttemptState && !liveQuizResult ? (
                      <p className="text-muted">Loading quiz...</p>
                    ) : liveQuizResult ? (
                      <div className="quiz-question-list">
                        {(() => {
                          const summary = summarizeQuizResult(liveQuizResult);
                          return (
                            <div className="quiz-score-shell">
                              <div>
                                <p className="eyebrow">Score Summary</p>
                                <div className="quiz-score-main">
                                  <strong>{liveQuizResult.score} / {liveQuizResult.max_score}</strong>
                                  <span>{liveQuizResult.percentage}%</span>
                                </div>
                              </div>
                              <div className="quiz-score-stats">
                                <span>Correct: <strong>{summary.correct}</strong></span>
                                <span>Wrong: <strong>{summary.wrong}</strong></span>
                                <span>Unanswered: <strong>{summary.unanswered}</strong></span>
                              </div>
                            </div>
                          );
                        })()}
                        {(liveQuizResult.results || []).map((item, index) => {
                          const resultState = item.is_correct ? "correct" : item.selected_option_key ? "wrong" : "unanswered";
                          return (
                            <div key={`${item.question_id || index}`} className={`quiz-question-simple result-${resultState}`}>
                              <div className="quiz-result-head">
                                <strong>Q{index + 1}: {item.question_text}</strong>
                                <span className={`chip result-chip-${resultState}`}>
                                  {item.is_correct ? "Correct" : item.selected_option_key ? "Wrong" : "Unanswered"}
                                </span>
                              </div>
                              <p className="text-muted text-small">
                                Your answer: {item.selected_option_key ? `${item.selected_option_key}. ${item.selected_option_text || ""}` : "No answer submitted"}
                              </p>
                              {item.correct_option_key && (
                                <p className="text-muted text-small">
                                  Correct answer: {item.correct_option_key}. {item.correct_option_text || ""}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="quiz-question-list">
                        {(liveQuizDetailQuery.data?.questions || liveAttemptState.quiz?.questions || []).map((question) => (
                          <div key={question.id} className="quiz-question-simple">
                            <strong>Q{question.order_index}: {question.question_text}</strong>
                            {(question.options || []).map((opt) => (
                              <label key={opt.id || opt.option_key} className="option-label">
                                <input
                                  type="radio"
                                  name={`live_quiz_${activeLiveQuizId}_${question.id}`}
                                  value={opt.option_key}
                                  checked={liveQuizAnswers[String(question.id)] === opt.option_key}
                                  onChange={(e) => {
                                    setLiveQuizAnswers((prev) => ({
                                      ...prev,
                                      [String(question.id)]: e.target.value,
                                    }));
                                  }}
                                  disabled={liveAttemptState?.status !== "IN_PROGRESS"}
                                />
                                {opt.option_key}. {opt.option_text}
                              </label>
                            ))}
                          </div>
                        ))}

                        {liveAttemptState?.status === "IN_PROGRESS" && (
                          <button
                            className="btn-primary"
                            onClick={() => submitClassworkLiveAttempt.mutate()}
                            disabled={submitClassworkLiveAttempt.isPending}
                          >
                            {submitClassworkLiveAttempt.isPending ? "Submitting..." : "Submit Quiz"}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            <section className="panel stack compact">
              <div className="section-header">
                <h3>Assignments</h3>
              </div>

              {isTeacher ? (
                <div className="assignment-actions">
                  <button
                    className="btn-secondary"
                    onClick={() => generateAssignment.mutate({ type: "ESSAY", title: "Assignment Draft" })}
                    disabled={generateAssignment.isPending}
                  >
                    {generateAssignment.isPending ? "Generating Assignment..." : "Create Assignment Draft (AI)"}
                  </button>
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
                                  due_date: draftEdit.due_date || null,
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
          <section className="panel stack compact people-shell">
            <div className="section-header">
              <h3>People</h3>
              <span className="chip">{studentCount} students</span>
            </div>
            <div className="people-grid">
              <div className="panel compact people-lead-card">
                <div className="teacher-avatar">{teacherInitial}</div>
                <div className="people-lead-copy">
                  <p className="eyebrow">Teacher</p>
                  <strong>{peopleQuery.data?.teacher?.name || "-"}</strong>
                  <p className="text-muted">{peopleQuery.data?.teacher?.email || ""}</p>
                </div>
                <div className="people-meta-row">
                  <div className="people-stat-pill">
                    <span>Invite Code</span>
                    <strong>{activeInviteCode}</strong>
                  </div>
                  <div className="people-stat-pill">
                    <span>Roster</span>
                    <strong>{studentCount} students</strong>
                  </div>
                </div>
              </div>

              <div className="panel compact student-roster">
                <div className="student-roster-header">
                  <div>
                    <p className="eyebrow">Students</p>
                    <strong>Class roster</strong>
                  </div>
                  <span className="chip">{studentCount} enrolled</span>
                </div>
                {studentCount === 0 ? (
                  <p className="text-muted">No students enrolled yet.</p>
                ) : (
                  <div className="student-roster-grid">
                    {(peopleQuery.data?.students || []).map((student) => (
                      <article key={student.id} className="student-roster-card">
                        <div className="student-avatar">
                          {(student.name || "S").trim().charAt(0).toUpperCase() || "S"}
                        </div>
                        <div className="student-roster-copy">
                          <strong>{student.name}</strong>
                          <p className="text-muted text-small">{student.email}</p>
                        </div>
                        <span className="chip">Student</span>
                      </article>
                    ))}
                  </div>
                )}
              </div>
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
              {isStudent && <span className="chip">{studentPracticeQuizzes.length + flashcardResults.length} active tools</span>}
            </div>
            <p className="text-muted">
              Build focused practice from your class modules. Quiz practice and flashcard review now live in separate stacked sections.
            </p>

            {isStudent && !labViewType && (
              <div className="lab-shell" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem' }}>
                <div 
                  className="panel compact stack lab-card" 
                  style={{ cursor: 'pointer', transition: 'all 0.2s' }}
                  onClick={() => setLabViewType('quiz')}
                >
                  <div className="lab-section-header">
                    <div>
                      <p className="eyebrow">Practice</p>
                      <h4>Quiz Session</h4>
                    </div>
                  </div>
                  <p className="lab-section-intro">Generate and take private practice quizzes based on your course modules.</p>
                </div>
                <div 
                  className="panel compact stack lab-card"
                  style={{ cursor: 'pointer', transition: 'all 0.2s' }}
                  onClick={() => setLabViewType('flashcards')}
                >
                  <div className="lab-section-header">
                    <div>
                      <p className="eyebrow">Revision</p>
                      <h4>Flashcards</h4>
                    </div>
                  </div>
                  <p className="lab-section-intro">Review concepts one card at a time with AI-generated flashcard decks.</p>
                </div>
              </div>
            )}

            {isStudent && labViewType === 'quiz' && (
              <div className="lab-shell">
                <button className="btn-secondary" onClick={() => setLabViewType(null)} style={{ marginBottom: '1rem' }}>← Back to Lab Menu</button>
                <div className="panel compact stack lab-card lab-section-card quiz-track">
                  <div className="lab-section-header">
                    <div>
                      <p className="eyebrow">Practice Quiz</p>
                      <h4>Generate a focused quiz session</h4>
                    </div>
                    <span className="chip">{studentPracticeQuizzes.length} quizzes</span>
                  </div>
                  <p className="lab-section-intro">
                    Pick one module or combine several, then launch a private quiz attempt from the generated set below.
                  </p>
                  <div className="actions" style={{ marginTop: 0 }}>
                    <button className={`btn-secondary ${labScopeMode === "single" ? "active-scope" : ""}`} onClick={() => setLabScopeMode("single")}>Single Module</button>
                    <button className={`btn-secondary ${labScopeMode === "multiple" ? "active-scope" : ""}`} onClick={() => setLabScopeMode("multiple")}>Multiple Modules</button>
                  </div>
                  <div className="actions" style={{ marginTop: 0 }}>
                    <input
                      className="input-field"
                      placeholder="Custom name (optional)"
                      value={practiceQuizName}
                      onChange={(e) => setPracticeQuizName(e.target.value)}
                    />
                    <label className="option-label" style={{ minWidth: "170px" }}>
                      Questions
                      <select
                        value={practiceQuestionCount}
                        onChange={(e) => setPracticeQuestionCount(Number(e.target.value))}
                      >
                        {[5, 8, 10, 12, 15, 20].map((count) => (
                          <option key={count} value={count}>{count}</option>
                        ))}
                      </select>
                    </label>
                  </div>
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
                  {studentPracticeQuizzes.length > 0 ? (
                    <>
                      <div className="quiz-list-simple">
                        {studentPracticeQuizzes.map((quiz) => {
                          const remembered = practiceQuizHistory[quiz.id];
                          const hasResult = Boolean(remembered?.result) || Boolean(quiz.has_submitted);
                          return (
                            <div key={quiz.id} className="quiz-list-row student-quiz-row">
                              <div className="quiz-list-meta">
                                <strong>{quiz.title}</strong>
                                <span className="text-muted text-small">{quizQuestionCount(quiz)} questions</span>
                              </div>
                              <div className="actions quiz-row-actions" style={{ marginTop: 0 }}>
                                <button
                                  className="btn-secondary"
                                  onClick={() => {
                                    const snapshot = practiceQuizHistory[quiz.id];
                                    setLabActiveQuizId(quiz.id);
                                    setLabAttemptState(null);
                                    setLabQuizAnswers(snapshot?.answers || {});
                                    setLabQuizResult(snapshot?.result || null);
                                  }}
                                >
                                  {hasResult ? "View Score" : "Open"}
                                </button>
                                <button
                                  className="btn-primary"
                                  onClick={() => {
                                    setLabActiveQuizId(quiz.id);
                                    setLabQuizResult(null);
                                    startLabAttempt.mutate(quiz.id);
                                  }}
                                  disabled={startLabAttempt.isPending}
                                >
                                  {startLabAttempt.isPending && startLabAttempt.variables === quiz.id
                                    ? "Loading..."
                                    : hasResult
                                      ? "Retake"
                                      : "Start"}
                                </button>
                                <button
                                  className="btn-secondary text-danger"
                                  onClick={() => {
                                    if (window.confirm(`Delete practice quiz "${quiz.title}"?`)) {
                                      deleteQuiz.mutate(quiz.id);
                                    }
                                  }}
                                  disabled={deleteQuiz.isPending}
                                >
                                  {deleteQuiz.isPending ? "Deleting..." : "Delete"}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {labActiveQuizId && labQuizDetailQuery.data && (
                        <div className="quiz-detail-simple">
                          <div className="section-header">
                            <h4>{labQuizDetailQuery.data.title}</h4>
                            <span className="chip">PRIVATE</span>
                          </div>

                          {labQuizResult ? (
                            <div className="quiz-question-list">
                              {(() => {
                                const summary = summarizeQuizResult(labQuizResult);
                                return (
                                  <div className="quiz-score-shell">
                                    <div>
                                      <p className="eyebrow">Last Result</p>
                                      <div className="quiz-score-main">
                                        <strong>{labQuizResult.score} / {labQuizResult.max_score}</strong>
                                        <span>{labQuizResult.percentage}%</span>
                                      </div>
                                    </div>
                                    <div className="quiz-score-stats">
                                      <span>Correct: <strong>{summary.correct}</strong></span>
                                      <span>Wrong: <strong>{summary.wrong}</strong></span>
                                      <span>Unanswered: <strong>{summary.unanswered}</strong></span>
                                    </div>
                                  </div>
                                );
                              })()}
                              {(labQuizResult.results || []).map((item, index) => {
                                const resultState = item.is_correct ? "correct" : item.selected_option_key ? "wrong" : "unanswered";
                                return (
                                  <div key={`${item.question_id || index}`} className={`quiz-question-simple result-${resultState}`}>
                                    <div className="quiz-result-head">
                                      <strong>Q{index + 1}: {item.question_text}</strong>
                                      <span className={`chip result-chip-${resultState}`}>
                                        {item.is_correct ? "Correct" : item.selected_option_key ? "Wrong" : "Unanswered"}
                                      </span>
                                    </div>
                                    <p className="text-muted text-small">
                                      Your answer: {item.selected_option_key ? `${item.selected_option_key}. ${item.selected_option_text || ""}` : "No answer submitted"}
                                    </p>
                                    {item.correct_option_key && (
                                      <p className="text-muted text-small">
                                        Correct answer: {item.correct_option_key}. {item.correct_option_text || ""}
                                      </p>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : labAttemptState ? (
                            <div className="quiz-question-list">
                              {(labAttemptState.quiz?.questions || labQuizDetailQuery.data.questions || []).map((question) => (
                                <div key={question.id} className="quiz-question-simple">
                                  <strong>Q{question.order_index}: {question.question_text}</strong>
                                  {(question.options || []).map((opt) => (
                                    <label key={opt.id || opt.option_key} className="option-label">
                                      <input
                                        type="radio"
                                        name={`lab_quiz_${question.id}`}
                                        value={opt.option_key}
                                        checked={labQuizAnswers[String(question.id)] === opt.option_key}
                                        onChange={(e) => setLabQuizAnswers((prev) => ({ ...prev, [String(question.id)]: e.target.value }))}
                                      />
                                      {opt.option_key}. {opt.option_text}
                                    </label>
                                  ))}
                                </div>
                              ))}

                              <button className="btn-primary" onClick={() => submitLabAttempt.mutate()} disabled={submitLabAttempt.isPending}>
                                {submitLabAttempt.isPending ? "Submitting..." : "Submit Quiz"}
                              </button>
                            </div>
                          ) : (
                            <p className="text-muted">Use Start or Retake from the quiz row above.</p>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="text-muted">Generate your first quiz to start practicing.</p>
                  )}
                </div>
              </div>
            )}

            {isStudent && labViewType === 'flashcards' && (
              <div className="lab-shell">
                <button className="btn-secondary" onClick={() => setLabViewType(null)} style={{ marginBottom: '1rem' }}>← Back to Lab Menu</button>
                <div className="panel compact stack lab-card lab-section-card flashcard-track">
                  <div className="lab-section-header">
                    <div>
                      <p className="eyebrow">Flashcards</p>
                      <h4>Review concepts one card at a time</h4>
                    </div>
                    <span className="chip">{flashcardResults.length} cards</span>
                  </div>
                  <p className="lab-section-intro">
                    Generate a revision stack from your current module selection and move through it at your own pace.
                  </p>
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
            {!isStudent && <p className="empty-state">Practice tools appear here for students enrolled in this classroom.</p>}
          </section>
        )}
      </div>

      <aside className="classroom-chat" style={{ display: activeTab === "ai" ? "block" : "none" }}>
        <ChatInterface courseId={courseId} />
      </aside>
    </div>
  );
}
