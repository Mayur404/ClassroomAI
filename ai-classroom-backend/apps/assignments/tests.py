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
        self.user = User.objects.create_user(
            email="student@example.com",
            password="testpass123",
            name="Student",
            role=UserRole.STUDENT,
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.course = Course.objects.create(
            teacher=self.user,
            name="AI Systems",
            extracted_topics=["Neural Networks", "Backpropagation", "Optimization"],
        )

    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_generate_assignment_accepts_date_only_due_date(self, _mock_call_ollama):
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

    def test_submission_endpoint_updates_existing_submission_instead_of_crashing(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 1",
            description="A short quiz",
            type="MCQ",
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
            due_date=timezone.now(),
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
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Submission.objects.filter(assignment=assignment, student=self.user).count(), 1)

        submission = Submission.objects.get(assignment=assignment, student=self.user)
        self.assertEqual(submission.answers, {"1": "A"})
        self.assertEqual(submission.ai_grade, 2)
        self.assertIn("Correct option: A", submission.ai_feedback["overall_feedback"])
        self.assertEqual(submission.score_breakdown[0]["correct_answer"], "A")
        self.assertIsNotNone(submission.submitted_at)

    def test_resubmission_refreshes_submission_timestamp(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz Timestamp",
            description="A short quiz",
            type="MCQ",
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
            due_date=timezone.now(),
        )

        first_response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "B"}},
            format="json",
        )
        self.assertEqual(first_response.status_code, 201)

        original_submission = Submission.objects.get(assignment=assignment, student=self.user)
        old_timestamp = timezone.now() - timedelta(days=1)
        Submission.objects.filter(id=original_submission.id).update(submitted_at=old_timestamp)

        second_response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": {"1": "A"}},
            format="json",
        )

        self.assertEqual(second_response.status_code, 200)
        original_submission.refresh_from_db()
        self.assertGreater(original_submission.submitted_at, old_timestamp)

    def test_submission_rejects_non_object_answers(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 2",
            description="Another short quiz",
            type="MCQ",
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
            due_date=timezone.now(),
        )

        response = self.client.post(
            reverse("submission-create", args=[assignment.id]),
            {"answers": ["A"]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_mcq_reasoning_includes_correct_answer_and_why_student_was_wrong(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 3",
            description="Reasoning check",
            type="MCQ",
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
            due_date=timezone.now(),
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
        assignment = Assignment.objects.create(
            course=self.course,
            title="Essay 1",
            description="Explain the concepts",
            type="ESSAY",
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
            due_date=timezone.now(),
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
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 3",
            description="A saved quiz",
            type="MCQ",
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
            due_date=timezone.now(),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.user,
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

    def test_submission_and_assignment_can_be_deleted_for_retake(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 4",
            description="Retake me",
            type="MCQ",
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
            due_date=timezone.now(),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.user,
            answers={"1": "B"},
            status="GRADED",
            ai_grade=0,
            ai_feedback={"overall_feedback": "Try again."},
            score_breakdown=[],
            graded_at=timezone.now(),
        )

        submission_response = self.client.delete(reverse("submission-detail", args=[submission.id]))
        assignment_response = self.client.delete(reverse("assignment-detail", args=[assignment.id]))

        self.assertEqual(submission_response.status_code, 204)
        self.assertEqual(assignment_response.status_code, 204)
        self.assertFalse(Submission.objects.filter(id=submission.id).exists())
        self.assertFalse(Assignment.objects.filter(id=assignment.id).exists())

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
