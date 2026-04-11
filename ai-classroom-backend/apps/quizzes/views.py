from django.db import transaction
from django.db.models import Avg, Count, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import ClassSchedule, Course

from .models import (
    AlertType,
    AttemptStatus,
    QuestionStatus,
    Quiz,
    QuizAlert,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizMode,
    QuizOption,
    QuizQuestion,
    QuizState,
)
from .serializers import (
    AttemptAnswerUpsertSerializer,
    AttemptSubmitSerializer,
    QuizAlertSerializer,
    QuizGenerateSerializer,
    QuizQuestionCreateSerializer,
    QuizQuestionTeacherSerializer,
    QuizStudentSerializer,
    QuizTeacherSerializer,
)
from .services import generate_session_mcqs
from .services import generate_scoped_mcqs


def _resolve_course_for_user(user, course_id: int) -> Course:
    if user.role == "TEACHER":
        return get_object_or_404(Course, id=course_id, teacher=user)
    return get_object_or_404(Course, id=course_id, enrollments__student=user)


def _resolve_quiz_for_user(user, quiz_id: int) -> Quiz:
    if user.role == "TEACHER":
        return get_object_or_404(
            Quiz.objects.select_related("course", "session"),
            id=quiz_id,
            course__teacher=user,
        )
    return get_object_or_404(
        Quiz.objects.select_related("course", "session"),
        id=quiz_id,
        course__enrollments__student=user,
    )


def _selected_scope_sessions(*, course: Course, anchor_session_id: int, data: dict) -> tuple[ClassSchedule, list[ClassSchedule], str]:
    all_sessions = list(ClassSchedule.objects.filter(course=course).order_by("class_number", "order_index"))
    if not all_sessions:
        raise PermissionDenied("No modules are available for this classroom.")

    module_scope = str(data.get("module_scope") or "single").strip().lower()
    include_all_modules = bool(data.get("include_all_modules", False))
    explicit_ids = [int(sid) for sid in (data.get("session_ids") or [])]

    anchor = next((item for item in all_sessions if item.id == anchor_session_id), None)
    if anchor is None:
        raise PermissionDenied("Invalid module selection.")

    if include_all_modules or module_scope == "all":
        return anchor, all_sessions, "all"

    if module_scope == "multiple":
        if not explicit_ids:
            explicit_ids = [anchor_session_id]
        selected = [item for item in all_sessions if item.id in set(explicit_ids)]
        if not selected:
            selected = [anchor]
        return anchor, selected, "multiple"

    return anchor, [anchor], "single"


def _create_low_score_alert(attempt: QuizAttempt):
    quiz = attempt.quiz
    if attempt.percentage >= float(quiz.low_score_threshold):
        return

    QuizAlert.objects.create(
        course=quiz.course,
        quiz=quiz,
        student=attempt.student,
        attempt=attempt,
        alert_type=AlertType.LOW_SCORE,
        threshold_percent=quiz.low_score_threshold,
        actual_percent=attempt.percentage,
    )


def _attempt_results_payload(attempt: QuizAttempt) -> list[dict]:
    detailed = []
    answer_rows = QuizAttemptAnswer.objects.filter(attempt=attempt).select_related("question").prefetch_related("question__options")
    for answer in answer_rows:
        options = list(answer.question.options.all())
        correct_opt = next((opt for opt in options if opt.is_correct), None)
        selected_opt = next((opt for opt in options if opt.option_key == answer.selected_option_key), None)
        correct_key = correct_opt.option_key if correct_opt else ""
        is_correct = bool(answer.selected_option_key and answer.selected_option_key == correct_key)
        detailed.append(
            {
                "question_id": answer.question_id,
                "question_text": answer.question.question_text,
                "selected_option_key": answer.selected_option_key,
                "selected_option_text": selected_opt.option_text if selected_opt else "",
                "correct_option_key": correct_key,
                "correct_option_text": correct_opt.option_text if correct_opt else "",
                "is_correct": is_correct,
                "explanation": answer.question.explanation,
                "source_citation": answer.question.source_citation,
                "options": [
                    {
                        "option_key": opt.option_key,
                        "option_text": opt.option_text,
                        "is_correct": bool(opt.is_correct),
                        "is_selected": bool(answer.selected_option_key and answer.selected_option_key == opt.option_key),
                    }
                    for opt in options
                ],
            }
        )
    return detailed


def _is_live_quiz_available_for_students(quiz: Quiz) -> bool:
    if quiz.mode != QuizMode.LIVE:
        return True
    if quiz.state != QuizState.PUBLISHED:
        return False
    now = timezone.now()
    if quiz.scheduled_for and quiz.scheduled_for > now:
        return False
    if quiz.due_at and quiz.due_at < now:
        return False
    return True


class QuizListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, course_id):
        course = _resolve_course_for_user(request.user, course_id)

        queryset = (
            Quiz.objects.filter(course=course)
            .select_related("session", "creator")
            .annotate(question_count_value=Count("questions", distinct=True))
        )
        if request.user.role == "TEACHER":
            queryset = queryset.exclude(mode=QuizMode.PRACTICE).filter(creator=request.user)
            data = QuizTeacherSerializer(queryset, many=True).data
        else:
            live_queryset = queryset.filter(
                mode=QuizMode.LIVE,
                state=QuizState.PUBLISHED,
            )
            practice_queryset = queryset.filter(mode=QuizMode.PRACTICE, creator=request.user)
            queryset = live_queryset | practice_queryset
            queryset = queryset.distinct()
            data = QuizStudentSerializer(queryset, many=True, context={"student_id": request.user.id}).data
            quiz_ids = [item["id"] for item in data]
            submitted_ids = set(
                QuizAttempt.objects.filter(
                    student=request.user,
                    status=AttemptStatus.SUBMITTED,
                    quiz_id__in=quiz_ids,
                ).values_list("quiz_id", flat=True)
            )
            for item in data:
                item["has_submitted"] = item["id"] in submitted_ids
        return Response(data)


class QuizGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id, session_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can generate live quizzes.")

        serializer = QuizGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        session = get_object_or_404(ClassSchedule, id=session_id, course=course)
        anchor_session, scoped_sessions, module_scope = _selected_scope_sessions(
            course=course,
            anchor_session_id=session.id,
            data=serializer.validated_data,
        )

        scope_topics = [item.topic for item in scoped_sessions if (item.topic or "").strip()]
        scope_ids = [item.id for item in scoped_sessions]

        question_count = serializer.validated_data.get("question_count", 8)
        generated_questions, snapshot = generate_scoped_mcqs(
            course_id=course.id,
            anchor_session_id=anchor_session.id,
            scope_topics=scope_topics,
            scope_session_ids=scope_ids,
            module_scope=module_scope,
            count=question_count,
        )

        generated_title = serializer.validated_data.get("title")
        if not generated_title:
            if module_scope == "single":
                generated_title = f"{anchor_session.topic} Quiz"
            elif module_scope == "multiple":
                generated_title = f"Mixed Modules Quiz ({len(scope_ids)} modules)"
            else:
                generated_title = "All Modules Quiz"

        with transaction.atomic():
            quiz = Quiz.objects.create(
                course=course,
                session=anchor_session,
                creator=request.user,
                mode=QuizMode.LIVE,
                state=QuizState.REVIEW,
                title=generated_title,
                instructions=serializer.validated_data.get("instructions", ""),
                time_limit_minutes=serializer.validated_data.get("time_limit_minutes"),
                scheduled_for=serializer.validated_data.get("scheduled_for"),
                due_at=serializer.validated_data.get("due_at"),
                is_private=False,
                shuffle_questions=serializer.validated_data.get("shuffle_questions", True),
                shuffle_options=serializer.validated_data.get("shuffle_options", True),
                low_score_threshold=serializer.validated_data.get("low_score_threshold", 60),
                source_material_snapshot=snapshot,
            )

            for idx, q in enumerate(generated_questions, start=1):
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    question_text=q.get("question_text", "").strip(),
                    difficulty=q.get("difficulty", "MEDIUM"),
                    order_index=idx,
                    status=QuestionStatus.AI_GENERATED,
                    source_citation=q.get("citation") or {},
                    explanation=q.get("explanation", ""),
                )
                correct_key = str(q.get("correct_option_key", "")).strip().upper()
                for opt in q.get("options", []):
                    key = str(opt.get("key", "")).strip().upper()
                    QuizOption.objects.create(
                        question=question,
                        option_key=key,
                        option_text=str(opt.get("text", "")).strip(),
                        is_correct=key == correct_key,
                    )

        return Response(QuizTeacherSerializer(quiz).data, status=status.HTTP_201_CREATED)


class PracticeQuizGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id, session_id):
        if request.user.role != "STUDENT":
            raise PermissionDenied("Only students can generate practice quizzes.")

        serializer = QuizGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        course = get_object_or_404(Course, id=course_id, enrollments__student=request.user)
        session = get_object_or_404(ClassSchedule, id=session_id, course=course)
        anchor_session, scoped_sessions, module_scope = _selected_scope_sessions(
            course=course,
            anchor_session_id=session.id,
            data=serializer.validated_data,
        )

        scope_topics = [item.topic for item in scoped_sessions if (item.topic or "").strip()]
        scope_ids = [item.id for item in scoped_sessions]

        question_count = serializer.validated_data.get("question_count", 8)
        generated_questions, snapshot = generate_scoped_mcqs(
            course_id=course.id,
            anchor_session_id=anchor_session.id,
            scope_topics=scope_topics,
            scope_session_ids=scope_ids,
            module_scope=module_scope,
            count=question_count,
        )

        generated_title = serializer.validated_data.get("title")
        if not generated_title:
            if module_scope == "single":
                generated_title = f"Practice: {anchor_session.topic}"
            elif module_scope == "multiple":
                generated_title = f"Practice: Mixed Modules ({len(scope_ids)})"
            else:
                generated_title = "Practice: All Modules"

        with transaction.atomic():
            quiz = Quiz.objects.create(
                course=course,
                session=anchor_session,
                creator=request.user,
                mode=QuizMode.PRACTICE,
                state=QuizState.PUBLISHED,
                title=generated_title,
                instructions=serializer.validated_data.get("instructions", ""),
                time_limit_minutes=serializer.validated_data.get("time_limit_minutes"),
                is_private=True,
                shuffle_questions=True,
                shuffle_options=True,
                source_material_snapshot=snapshot,
            )

            for idx, q in enumerate(generated_questions, start=1):
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    question_text=q.get("question_text", "").strip(),
                    difficulty=q.get("difficulty", "MEDIUM"),
                    order_index=idx,
                    status=QuestionStatus.AI_GENERATED,
                    source_citation=q.get("citation") or {},
                    explanation=q.get("explanation", ""),
                )
                correct_key = str(q.get("correct_option_key", "")).strip().upper()
                for opt in q.get("options", []):
                    key = str(opt.get("key", "")).strip().upper()
                    QuizOption.objects.create(
                        question=question,
                        option_key=key,
                        option_text=str(opt.get("text", "")).strip(),
                        is_correct=key == correct_key,
                    )

        return Response(
            QuizStudentSerializer(
                quiz,
                context={"include_questions": True, "student_id": request.user.id},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class QuizDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, quiz_id):
        quiz = _resolve_quiz_for_user(request.user, quiz_id)
        if request.user.role == "TEACHER":
            if quiz.mode == QuizMode.PRACTICE and quiz.creator_id != request.user.id:
                raise PermissionDenied("Private student practice quizzes are not visible to teachers.")
            return Response(QuizTeacherSerializer(quiz).data)

        if quiz.mode == QuizMode.PRACTICE and quiz.creator_id != request.user.id:
            raise PermissionDenied("This practice quiz is private.")
        if not _is_live_quiz_available_for_students(quiz):
            raise PermissionDenied("This quiz is not available right now.")

        payload = QuizStudentSerializer(
            quiz,
            context={"include_questions": True, "student_id": request.user.id},
        ).data
        latest_attempt = QuizAttempt.objects.filter(
            quiz=quiz,
            student=request.user,
            status=AttemptStatus.SUBMITTED,
        ).order_by("-submitted_at").first()
        if latest_attempt:
            payload["latest_attempt"] = {
                "attempt_id": latest_attempt.id,
                "score": latest_attempt.score,
                "max_score": latest_attempt.max_score,
                "percentage": latest_attempt.percentage,
                "submitted_at": latest_attempt.submitted_at,
                "results": _attempt_results_payload(latest_attempt),
            }

        return Response(payload)

    def patch(self, request, quiz_id):
        quiz = _resolve_quiz_for_user(request.user, quiz_id)
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can edit quizzes.")
        if quiz.mode == QuizMode.PRACTICE and quiz.creator_id != request.user.id:
            raise PermissionDenied("Private student practice quizzes are not editable by teachers.")
        if quiz.state not in {QuizState.DRAFT, QuizState.REVIEW}:
            return Response({"detail": "Only draft/review quizzes are editable."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuizTeacherSerializer(quiz, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, quiz_id):
        quiz = _resolve_quiz_for_user(request.user, quiz_id)

        if request.user.role == "TEACHER":
            if quiz.creator_id != request.user.id:
                raise PermissionDenied("Only the quiz creator can delete this quiz.")
            quiz.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        if quiz.mode != QuizMode.PRACTICE or quiz.creator_id != request.user.id:
            raise PermissionDenied("Students can only delete their own practice quizzes.")

        quiz.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuizPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, quiz_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can publish quizzes.")

        quiz = get_object_or_404(Quiz, id=quiz_id, course__teacher=request.user, creator=request.user)
        if quiz.mode != QuizMode.LIVE:
            return Response({"detail": "Only live quizzes can be published."}, status=status.HTTP_400_BAD_REQUEST)

        questions = list(quiz.questions.prefetch_related("options"))
        if not questions:
            return Response({"detail": "Quiz has no questions."}, status=status.HTTP_400_BAD_REQUEST)

        for q in questions:
            options = list(q.options.all())
            if len(options) != 4:
                return Response({"detail": f"Question {q.id} must have exactly 4 options."}, status=status.HTTP_400_BAD_REQUEST)
            correct_count = sum(1 for opt in options if opt.is_correct)
            if correct_count != 1:
                return Response({"detail": f"Question {q.id} must have exactly one correct option."}, status=status.HTTP_400_BAD_REQUEST)

        quiz.state = QuizState.PUBLISHED
        quiz.published_at = timezone.now()
        quiz.save(update_fields=["state", "published_at", "updated_at"])
        return Response(QuizTeacherSerializer(quiz).data)


class QuizQuestionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, quiz_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can add quiz questions.")

        quiz = get_object_or_404(Quiz, id=quiz_id, course__teacher=request.user, creator=request.user)
        if quiz.state not in {QuizState.DRAFT, QuizState.REVIEW}:
            return Response({"detail": "Only draft/review quizzes are editable."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuizQuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_max = quiz.questions.aggregate(max_idx=Max("order_index")).get("max_idx") or 0
        question = QuizQuestion.objects.create(
            quiz=quiz,
            question_text=serializer.validated_data["question_text"],
            difficulty=serializer.validated_data.get("difficulty", "MEDIUM"),
            order_index=current_max + 1,
            status=QuestionStatus.TEACHER_ADDED,
            explanation=serializer.validated_data.get("explanation", ""),
        )

        for option in serializer.validated_data["options"]:
            QuizOption.objects.create(
                question=question,
                option_key=option["option_key"],
                option_text=option["option_text"],
                is_correct=option["is_correct"],
            )

        return Response(QuizQuestionTeacherSerializer(question).data, status=status.HTTP_201_CREATED)


class QuizQuestionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, question_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can edit quiz questions.")

        question = get_object_or_404(
            QuizQuestion.objects.select_related("quiz"),
            id=question_id,
            quiz__course__teacher=request.user,
            quiz__creator=request.user,
        )
        if question.quiz.state not in {QuizState.DRAFT, QuizState.REVIEW}:
            return Response({"detail": "Only draft/review quizzes are editable."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuizQuestionTeacherSerializer(question, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, question_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can delete quiz questions.")

        question = get_object_or_404(
            QuizQuestion.objects.select_related("quiz"),
            id=question_id,
            quiz__course__teacher=request.user,
            quiz__creator=request.user,
        )
        if question.quiz.state not in {QuizState.DRAFT, QuizState.REVIEW}:
            return Response({"detail": "Only draft/review quizzes are editable."}, status=status.HTTP_400_BAD_REQUEST)
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuizAttemptStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, quiz_id):
        if request.user.role != "STUDENT":
            raise PermissionDenied("Only students can attempt quizzes.")

        quiz = get_object_or_404(Quiz.objects.select_related("course"), id=quiz_id, course__enrollments__student=request.user)
        if quiz.mode == QuizMode.PRACTICE and quiz.creator_id != request.user.id:
            return Response({"detail": "This practice quiz is private."}, status=status.HTTP_403_FORBIDDEN)

        if quiz.mode == QuizMode.LIVE:
            submitted = QuizAttempt.objects.filter(
                quiz=quiz,
                student=request.user,
                status=AttemptStatus.SUBMITTED,
            ).order_by("-submitted_at").first()
            if submitted:
                quiz_payload = QuizStudentSerializer(
                    quiz,
                    context={"include_questions": True, "student_id": request.user.id},
                ).data
                return Response(
                    {
                        "attempt_id": submitted.id,
                        "quiz": quiz_payload,
                        "status": submitted.status,
                        "score": submitted.score,
                        "max_score": submitted.max_score,
                        "percentage": submitted.percentage,
                        "feedback_released": submitted.feedback_released,
                        "results": _attempt_results_payload(submitted),
                        "locked": True,
                    }
                )

        if not _is_live_quiz_available_for_students(quiz):
            return Response({"detail": "Quiz is not live."}, status=status.HTTP_400_BAD_REQUEST)

        existing = QuizAttempt.objects.filter(
            quiz=quiz,
            student=request.user,
            status=AttemptStatus.IN_PROGRESS,
        ).order_by("-started_at").first()

        if existing:
            attempt = existing
        else:
            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                student=request.user,
                status=AttemptStatus.IN_PROGRESS,
                is_practice=(quiz.mode == QuizMode.PRACTICE),
            )
            for question in quiz.questions.all():
                QuizAttemptAnswer.objects.create(attempt=attempt, question=question)

        quiz_payload = QuizStudentSerializer(
            quiz,
            context={"include_questions": True, "student_id": request.user.id},
        ).data
        return Response({"attempt_id": attempt.id, "quiz": quiz_payload, "status": attempt.status})


class QuizAttemptAnswerUpsertView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, attempt_id):
        attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz"), id=attempt_id, student=request.user)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return Response({"detail": "Attempt is already submitted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AttemptAnswerUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data["answers"]

        question_map = {str(q.id): q for q in attempt.quiz.questions.all()}
        for qid, selected in answers.items():
            question = question_map.get(str(qid))
            if not question:
                continue
            selected_key = (selected or "").strip().upper()[:1]
            if selected_key not in {"A", "B", "C", "D"}:
                continue
            QuizAttemptAnswer.objects.filter(attempt=attempt, question=question).update(selected_option_key=selected_key)

        return Response({"saved": True})


class QuizAttemptSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, attempt_id):
        attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz", "quiz__course"), id=attempt_id, student=request.user)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return Response({"detail": "Attempt is already submitted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AttemptSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("answers"):
            for qid, selected in serializer.validated_data["answers"].items():
                selected_key = (selected or "").strip().upper()[:1]
                if selected_key not in {"A", "B", "C", "D"}:
                    continue
                QuizAttemptAnswer.objects.filter(attempt=attempt, question_id=qid).update(selected_option_key=selected_key)

        score = 0.0
        max_score = 0.0
        answer_rows = QuizAttemptAnswer.objects.filter(attempt=attempt).select_related("question").prefetch_related("question__options")
        for answer in answer_rows:
            max_score += 1.0
            options = list(answer.question.options.all())
            correct_opt = next((opt for opt in options if opt.is_correct), None)
            selected_opt = next((opt for opt in options if opt.option_key == answer.selected_option_key), None)
            correct_key = correct_opt.option_key if correct_opt else ""
            is_correct = bool(answer.selected_option_key and answer.selected_option_key == correct_key)
            marks = 1.0 if is_correct else 0.0
            score += marks

            answer.is_correct = is_correct
            answer.marks_awarded = marks
            answer.save(update_fields=["is_correct", "marks_awarded", "updated_at"])

        percentage = round((score / max_score) * 100, 2) if max_score else 0.0
        attempt.status = AttemptStatus.SUBMITTED
        attempt.score = score
        attempt.max_score = max_score
        attempt.percentage = percentage
        attempt.submitted_at = timezone.now()
        attempt.feedback_released = True
        attempt.save(
            update_fields=[
                "status",
                "score",
                "max_score",
                "percentage",
                "submitted_at",
                "feedback_released",
            ]
        )

        if attempt.quiz.mode == QuizMode.LIVE:
            _create_low_score_alert(attempt)

        detailed = _attempt_results_payload(attempt)

        return Response(
            {
                "attempt_id": attempt.id,
                "score": score,
                "max_score": max_score,
                "percentage": percentage,
                "feedback_released": True,
                "results": detailed,
            }
        )


class QuizAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, quiz_id):
        if request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can view quiz analytics.")

        quiz = get_object_or_404(Quiz, id=quiz_id, course__teacher=request.user, creator=request.user)
        attempts = QuizAttempt.objects.filter(quiz=quiz, status=AttemptStatus.SUBMITTED).select_related("student")
        metrics = attempts.aggregate(avg=Avg("percentage"), count=Count("id"))
        low_students = attempts.filter(percentage__lt=float(quiz.low_score_threshold))

        return Response(
            {
                "quiz_id": quiz.id,
                "title": quiz.title,
                "attempt_count": metrics.get("count") or 0,
                "average_percentage": round(float(metrics.get("avg") or 0), 2),
                "threshold": quiz.low_score_threshold,
                "students": [
                    {
                        "student_id": att.student_id,
                        "student_name": att.student.name,
                        "score": att.score,
                        "max_score": att.max_score,
                        "percentage": att.percentage,
                        "submitted_at": att.submitted_at,
                    }
                    for att in attempts.order_by("percentage")
                ],
                "low_performers": [
                    {
                        "student_id": att.student_id,
                        "student_name": att.student.name,
                        "percentage": att.percentage,
                    }
                    for att in low_students.order_by("percentage")
                ],
            }
        )


class CourseQuizAlertListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuizAlertSerializer

    def get_queryset(self):
        if self.request.user.role != "TEACHER":
            raise PermissionDenied("Only teachers can view alerts.")
        course = get_object_or_404(Course, id=self.kwargs["course_id"], teacher=self.request.user)
        return QuizAlert.objects.filter(course=course).select_related("student", "quiz", "attempt")
