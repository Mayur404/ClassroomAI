from unittest import mock

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.courses.models import Course, CourseMaterial, Enrollment
from apps.users.models import User, UserRole


class ChatFallbackTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="teacher@example.com",
            password="testpass123",
            name="Teacher",
            role=UserRole.TEACHER,
        )
        self.user = User.objects.create_user(
            email="chat@example.com",
            password="testpass123",
            name="Chat User",
            role=UserRole.STUDENT,
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.course = Course.objects.create(teacher=self.teacher, name="Algorithms")
        Enrollment.objects.create(course=self.course, student=self.user)
        CourseMaterial.objects.create(
            course=self.course,
            title="Recursion Notes",
            content_text="Recursion solves a problem by reducing it to smaller versions of the same problem.",
            extracted_topics=["Recursion"],
            parse_status="SUCCESS",
        )

    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_chat_stays_grounded_in_pdf_when_llm_is_unavailable(self, _mock_call_ollama):
        response = self.client.post(
            reverse("chat-ask", args=[self.course.id]),
            {"message": "What is recursion?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recursion solves a problem", response.data["answer_text"])
        self.assertIn("Source: Recursion Notes page 1.", response.data["answer_text"])
        self.assertGreaterEqual(len(response.data["sources"]), 1)

    @mock.patch("apps.ai_service.services.call_ollama")
    def test_chat_returns_exact_pdf_wording_for_fact_lookup(self, mock_call_ollama):
        response = self.client.post(
            reverse("chat-ask", args=[self.course.id]),
            {"message": "What is recursion?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Recursion solves a problem by reducing it to smaller versions of the same problem.",
            response.data["answer_text"],
        )
        mock_call_ollama.assert_not_called()

    @mock.patch("apps.ai_service.services.call_ollama", return_value="Recursion breaks a problem into smaller versions of the same problem.")
    def test_chat_reuses_cached_answer_for_repeated_explanatory_question(self, mock_call_ollama):
        first = self.client.post(
            reverse("chat-ask", args=[self.course.id]),
            {"message": "Explain why recursion is useful."},
            format="json",
        )
        second = self.client.post(
            reverse("chat-ask", args=[self.course.id]),
            {"message": "Explain why recursion is useful."},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["answer_text"], second.data["answer_text"])
        mock_call_ollama.assert_called_once()

