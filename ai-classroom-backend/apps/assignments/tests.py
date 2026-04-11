from unittest import mock
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.assignments.models import Assignment
from apps.courses.models import Course
from apps.submissions.models import Submission
from apps.users.models import User, UserRole


class AssignmentWorkflowTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="teacher@example.com",
            password="testpass123",
            name="Teacher",
            role=UserRole.TEACHER,
        )
        self.student = User.objects.create_user(
            email="student@example.com",
            password="testpass123",
            name="Student",
            role=UserRole.STUDENT,
        )
        self.teacher_token = Token.objects.create(user=self.teacher)
        self.student_token = Token.objects.create(user=self.student)
        self.course = Course.objects.create(
            teacher=self.teacher,
            name="AI Systems",
            extracted_topics=["Neural Networks", "Backpropagation", "Optimization"],
        )
        self.course.enrollments.create(student=self.student)
        self.authenticate(self.teacher)

    def authenticate(self, user):
        token = self.teacher_token if user == self.teacher else self.student_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_generate_assignment_accepts_date_only_due_date(self, _mock_call_ollama):
        self.authenticate(self.teacher)
        response = self.client.post(
            reverse("assignment-generate", args=[self.course.id]),
            {
                "title": "Quick Quiz",
                "type": "MCQ",
                "due_date": "2026-03-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "MCQ")
        self.assertGreater(len(response.data["questions"]), 0)
        self.assertGreater(response.data["total_marks"], 0)
        self.assertTrue(response.data["answer_key"])
        first_answer = response.data["answer_key"]["1"]
        self.assertIn("correct_option", first_answer)
        self.assertIn("explanation", first_answer)
        self.assertIn("2026-03-30", response.data["due_date"])

    def test_submission_endpoint_rejects_second_attempt_when_retakes_are_disabled(self):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 1",
            description="A short quiz",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": "A"},
            due_date=timezone.now() + timedelta(days=1),
        )

        first_response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "B"}},
            format="json",
        )
        second_response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "A"}},
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(Submission.objects.filter(assignment=assignment, student=self.student).count(), 1)

        submission = Submission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(submission.answers, {"1": "B"})
        self.assertEqual(submission.ai_grade, 0)
        self.assertIn("already submitted", second_response.data["detail"])
        self.assertIsNotNone(submission.submitted_at)

    def test_student_cannot_delete_submission_to_force_a_retake(self):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz Timestamp",
            description="A short quiz",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": "A"},
            due_date=timezone.now() + timedelta(days=1),
        )

        first_response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "B"}},
            format="json",
        )
        self.assertEqual(first_response.status_code, 201)

        original_submission = Submission.objects.get(assignment=assignment, student=self.student)
        delete_response = self.client.delete(reverse("submission-detail", args=[original_submission.id]))

        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Submission.objects.filter(id=original_submission.id).exists())

    def test_submission_rejects_non_object_answers(self):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 2",
            description="Another short quiz",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": {"correct_option": "A", "explanation": "A is correct."}},
            due_date=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": ["A"]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_mcq_reasoning_includes_correct_answer_and_why_student_was_wrong(self):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 3",
            description="Reasoning check",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": {"correct_option": "A", "explanation": "A is correct because it matches the course concept."}},
            due_date=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "B"}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = response.data["score_breakdown"][0]
        self.assertEqual(review["correct_answer"], "A")
        self.assertIn("The correct answer is A.", review["reasoning"])
        self.assertIn("You got it wrong because you selected B", review["reasoning"])
        self.assertEqual(review["feedback"], review["reasoning"])

    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_essay_submission_returns_per_question_reasoning(self, _mock_call_ollama):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Essay 1",
            description="Explain the concepts",
            type="ESSAY",
            status="PUBLISHED",
            total_marks=20,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Explain backpropagation.",
                    "marks": 10,
                },
                {
                    "question_number": 2,
                    "prompt": "Explain optimization.",
                    "marks": 10,
                },
            ],
            rubric=[],
            due_date=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {
                "answers": {
                    "1": "Backpropagation computes gradients and updates network weights across layers.",
                    "2": "Optimization chooses parameter updates to reduce loss over time.",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["score_breakdown"]), 2)
        self.assertIn("student_answer", response.data["score_breakdown"][0])
        self.assertIn("feedback", response.data["score_breakdown"][0])
        self.assertIn("answer_review", response.data["ai_feedback"])

    def test_assignment_list_includes_latest_submission(self):
        self.authenticate(self.student)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 3",
            description="A saved quiz",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": {"correct_option": "A", "explanation": "A is correct."}},
            due_date=timezone.now() + timedelta(days=1),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            answers={"1": "A"},
            status="GRADED",
            ai_grade=2,
            ai_feedback={"overall_feedback": "Nice work."},
            score_breakdown=[
                {
                    "question_number": 1,
                    "score": 2,
                    "max_score": 2,
                    "feedback": "Correct.",
                    "student_answer": "A",
                    "correct_answer": "A",
                }
            ],
            graded_at=timezone.now(),
        )

        response = self.client.get(reverse("assignment-list", args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["latest_submission"]["id"], submission.id)
        self.assertEqual(response.data[0]["latest_submission"]["answers"], {"1": "A"})

    def test_teacher_can_override_assignment_marks_manually(self):
        self.authenticate(self.teacher)
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 4",
            description="Needs review",
            type="ESSAY",
            status="PUBLISHED",
            total_marks=10,
            questions=[
                {
                    "question_number": 1,
                    "question_number": 1,
                    "prompt": "Explain gradient descent.",
                    "marks": 10,
                }
            ],
            rubric=[{"question_number": 1, "criteria": ["Mention optimization and reducing loss."]}],
            due_date=timezone.now() + timedelta(days=1),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            answers={"1": "Gradient descent updates weights."},
            status="GRADED",
            ai_grade=6,
            ai_feedback={"overall_feedback": "Good start."},
            score_breakdown=[
                {
                    "question_number": 1,
                    "score": 6,
                    "max_score": 10,
                    "feedback": "Needs more detail.",
                }
            ],
            graded_at=timezone.now(),
        )

        response = self.client.patch(
            reverse("submission-teacher-grade", args=[submission.id]),
            {"teacher_grade": 8.5, "teacher_feedback": "Relevant answer, but one core step was missing."},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.teacher_grade, 8.5)
        self.assertEqual(submission.final_grade, 8.5)
        self.assertEqual(response.data["grade_source"], "TEACHER")
        self.assertEqual(response.data["final_grade"], 8.5)
        self.assertEqual(response.data["teacher_feedback"], "Relevant answer, but one core step was missing.")

    @mock.patch("apps.assignments.views.generate_assignment_for_course")
    def test_assignment_generation_prefers_completed_schedule_topics(self, mock_generate_assignment):
        self.course.schedule_items.create(
            order_index=1,
            class_number=1,
            topic="Neural Networks",
            subtopics=["Perceptron", "Activation functions"],
            learning_objectives=["Explain a perceptron."],
            duration_minutes=60,
            status="COMPLETED",
        )
        self.course.schedule_items.create(
            order_index=2,
            class_number=2,
            topic="Backpropagation",
            subtopics=["Chain rule"],
            learning_objectives=["Compute gradients."],
            duration_minutes=60,
            status="PLANNED",
        )
        mock_generate_assignment.return_value = {
            "title": "Completed Scope Quiz",
            "description": "Only completed material.",
            "type": "MCQ",
            "total_marks": 2,
            "questions": [
                {
                    "question_number": 1,
                    "prompt": "Which topic is completed?",
                    "options": ["Neural Networks", "Backpropagation", "Optimization", "Data Cleaning"],
                    "marks": 2,
                }
            ],
            "rubric": [{"question_number": 1, "criteria": ["Correct option only."]}],
            "answer_key": {"1": {"correct_option": "Neural Networks", "explanation": "Completed topic."}},
        }

        response = self.client.post(
            reverse("assignment-generate", args=[self.course.id]),
            {
                "title": "Completed Scope Quiz",
                "type": "MCQ",
                "due_date": "2026-03-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        kwargs = mock_generate_assignment.call_args.kwargs
        self.assertEqual(kwargs["covered_topics"], ["Neural Networks"])
        self.assertEqual(
            kwargs["covered_outline"],
            [
                {
                    "topic": "Neural Networks",
                    "subtopics": ["Perceptron", "Activation functions"],
                    "learning_objectives": ["Explain a perceptron."],
                }
            ],
        )
        self.assertEqual(response.data["covered_until_class"], 1)

    @mock.patch("apps.assignments.views.generate_assignment_for_course")
    def test_assignment_generation_uses_first_planned_topics_when_nothing_completed(self, mock_generate_assignment):
        for index, topic in enumerate(["Arrays", "Stacks", "Queues", "Trees"], start=1):
            self.course.schedule_items.create(
                order_index=index,
                class_number=index,
                topic=topic,
                subtopics=[f"{topic} basics"],
                learning_objectives=[f"Explain {topic}."],
                duration_minutes=60,
                status="PLANNED",
            )

        mock_generate_assignment.return_value = {
            "title": "Planned Scope Quiz",
            "description": "Upcoming material only.",
            "type": "MCQ",
            "total_marks": 6,
            "questions": [
                {
                    "question_number": 1,
                    "prompt": "Pick the correct topic.",
                    "options": ["Arrays", "Graphs", "Sorting", "Hashing"],
                    "marks": 2,
                },
                {
                    "question_number": 2,
                    "prompt": "Pick the correct topic.",
                    "options": ["Stacks", "Graphs", "Sorting", "Hashing"],
                    "marks": 2,
                },
                {
                    "question_number": 3,
                    "prompt": "Pick the correct topic.",
                    "options": ["Queues", "Graphs", "Sorting", "Hashing"],
                    "marks": 2,
                },
            ],
            "rubric": [
                {"question_number": 1, "criteria": ["Correct option only."]},
                {"question_number": 2, "criteria": ["Correct option only."]},
                {"question_number": 3, "criteria": ["Correct option only."]},
            ],
            "answer_key": {
                "1": {"correct_option": "Arrays", "explanation": "Covered in the first planned scope."},
                "2": {"correct_option": "Stacks", "explanation": "Covered in the first planned scope."},
                "3": {"correct_option": "Queues", "explanation": "Covered in the first planned scope."},
            },
        }

        response = self.client.post(
            reverse("assignment-generate", args=[self.course.id]),
            {
                "title": "Planned Scope Quiz",
                "type": "MCQ",
                "due_date": "2026-03-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        kwargs = mock_generate_assignment.call_args.kwargs
        self.assertEqual(kwargs["covered_topics"], ["Arrays", "Stacks", "Queues"])
        self.assertEqual(response.data["covered_until_class"], 3)


class AssignmentTeacherVisibilityTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="teacher@example.com",
            password="testpass123",
            name="Teacher",
            role=UserRole.TEACHER,
        )
        self.student = User.objects.create_user(
            email="student2@example.com",
            password="testpass123",
            name="Student Two",
            role=UserRole.STUDENT,
        )
        teacher_token = Token.objects.create(user=self.teacher)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {teacher_token.key}")

        self.course = Course.objects.create(
            teacher=self.teacher,
            name="Neural Systems",
            extracted_topics=["Transformers"],
        )
        self.course.enrollments.create(student=self.student)

    def test_teacher_assignment_list_includes_student_submissions(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Essay Review",
            description="Explain the topic",
            type="ESSAY",
            status="PUBLISHED",
            total_marks=20,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Explain attention.",
                    "marks": 20,
                }
            ],
            due_date=timezone.now() + timedelta(days=1),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            answers={"1": "Attention helps the model focus on relevant tokens."},
            status="GRADED",
            ai_grade=16,
            ai_feedback={"overall_feedback": "Good answer."},
            score_breakdown=[
                {
                    "question_number": 1,
                    "score": 16,
                    "max_score": 20,
                    "feedback": "Solid explanation.",
                }
            ],
            graded_at=timezone.now(),
        )

        response = self.client.get(reverse("assignment-list", args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["question_count"], 1)
        self.assertEqual(response.data[0]["teacher_submission_summary"]["submitted_count"], 1)
        self.assertEqual(response.data[0]["teacher_submission_summary"]["pending_count"], 0)
        self.assertEqual(response.data[0]["class_submissions"][0]["id"], submission.id)
        self.assertEqual(response.data[0]["class_submissions"][0]["student_name"], "Student Two")
        self.assertEqual(
            response.data[0]["class_submissions"][0]["answers"],
            {"1": "Attention helps the model focus on relevant tokens."},
        )

    def test_student_cannot_submit_after_assignment_due_date(self):
        student_token = Token.objects.create(user=self.student)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {student_token.key}")

        assignment = Assignment.objects.create(
            course=self.course,
            title="Closed Quiz",
            description="Too late",
            type="MCQ",
            status="PUBLISHED",
            total_marks=2,
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Pick the correct answer.",
                    "options": ["A", "B", "C", "D"],
                    "marks": 2,
                }
            ],
            answer_key={"1": {"correct_option": "A", "explanation": "A is correct."}},
            due_date=timezone.now() - timedelta(minutes=5),
        )

        response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "A"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("due date has passed", response.data["detail"])
