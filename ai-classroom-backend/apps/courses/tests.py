from unittest import mock

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.courses.models import Course, ParseStatus
from apps.users.models import User, UserRole


class CourseMaterialWorkflowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="learner@example.com",
            password="testpass123",
            name="Learner",
            role=UserRole.STUDENT,
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.course = Course.objects.create(teacher=self.user, name="Data Structures")

    @mock.patch(
        "apps.courses.views.index_course_materials",
        return_value={
            "status": "SUCCESS",
            "topics": ["Arrays", "Linked Lists"],
            "num_chunks": 2,
            "embedding_backend": "hash-fallback",
        },
    )
    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_upload_and_delete_material_rebuilds_topics_and_schedule(self, _mock_call_ollama, _mock_index):
        upload_response = self.client.post(
            reverse("course-syllabus", args=[self.course.id]),
            {
                "title": "Week 1 Notes",
                "syllabus_text": "Week 1: Arrays are contiguous. Week 2: Linked lists are node-based. Late submissions lose 10% per day.",
            },
        )

        self.assertEqual(upload_response.status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.extracted_topics, ["Arrays", "Linked Lists"])
        self.assertEqual(self.course.syllabus_parse_status, ParseStatus.SUCCESS)
        self.assertEqual(self.course.materials.count(), 1)
        self.assertEqual(self.course.schedule_items.count(), 2)
        self.assertIn("Key ideas behind Arrays", self.course.schedule_items.first().subtopics)
        self.assertEqual(self.course.num_assignments, 2)
        self.assertEqual(self.course.assignment_weightage, "25%")
        self.assertEqual(self.course.parse_metadata["material_count"], 1)
        self.assertEqual(self.course.parse_metadata["topic_count"], 2)
        self.assertEqual(self.course.parse_metadata["embedding_backend"], "hash-fallback")
        self.assertTrue(any("Late submissions lose 10% per day" in item for item in self.course.extracted_policies))
        self.assertEqual(upload_response.data["material_count"], 1)
        self.assertEqual(upload_response.data["schedule_progress_percent"], 0)
        self.assertEqual(upload_response.data["next_class_topic"], "Arrays")

        material = self.course.materials.first()
        delete_response = self.client.delete(reverse("material-delete", args=[material.id]))

        self.assertEqual(delete_response.status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.extracted_topics, [])
        self.assertEqual(self.course.syllabus_parse_status, ParseStatus.PENDING)
        self.assertEqual(self.course.materials.count(), 0)
        self.assertEqual(self.course.schedule_items.count(), 0)

    def test_upload_rejects_too_short_text(self):
        response = self.client.post(
            reverse("course-syllabus", args=[self.course.id]),
            {
                "title": "Tiny Note",
                "syllabus_text": "Too short for analysis.",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_schedule_complete_endpoint_can_toggle_back_to_planned(self):
        schedule_item = self.course.schedule_items.create(
            order_index=1,
            class_number=1,
            topic="Arrays",
            subtopics=["Array traversal"],
            learning_objectives=["Explain array traversal."],
            duration_minutes=60,
        )

        complete_response = self.client.post(
            reverse("schedule-complete", args=[schedule_item.id]),
            {"completed": True},
            format="json",
        )
        reset_response = self.client.post(
            reverse("schedule-complete", args=[schedule_item.id]),
            {"completed": False},
            format="json",
        )

        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(reset_response.status_code, 200)
        schedule_item.refresh_from_db()
        self.assertEqual(schedule_item.status, "PLANNED")

    @mock.patch(
        "apps.courses.views.index_course_materials",
        side_effect=[
            {
                "status": "SUCCESS",
                "topics": ["Arrays", "Linked Lists"],
                "num_chunks": 2,
                "embedding_backend": "hash-fallback",
            },
            {
                "status": "SUCCESS",
                "topics": ["Arrays", "Linked Lists", "Trees"],
                "num_chunks": 3,
                "embedding_backend": "hash-fallback",
            },
        ],
    )
    @mock.patch("apps.ai_service.services.call_ollama", side_effect=RuntimeError("offline"))
    def test_rebuilding_schedule_preserves_completed_items_for_matching_topics(self, _mock_call_ollama, _mock_index):
        first_upload = self.client.post(
            reverse("course-syllabus", args=[self.course.id]),
            {
                "title": "Week 1 Notes",
                "syllabus_text": "Week 1: Arrays. Week 2: Linked lists. Late submissions lose 10% per day.",
            },
        )
        self.assertEqual(first_upload.status_code, 200)

        first_item = self.course.schedule_items.get(class_number=1)
        complete_response = self.client.post(
            reverse("schedule-complete", args=[first_item.id]),
            {"completed": True},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)

        second_upload = self.client.post(
            reverse("course-syllabus", args=[self.course.id]),
            {
                "title": "Week 2 Notes",
                "syllabus_text": "Week 1: Arrays. Week 2: Linked lists. Week 3: Trees and traversals.",
            },
        )
        self.assertEqual(second_upload.status_code, 200)

        self.course.refresh_from_db()
        rebuilt_arrays_item = self.course.schedule_items.get(topic="Arrays")
        rebuilt_trees_item = self.course.schedule_items.get(topic="Trees")
        self.assertEqual(rebuilt_arrays_item.status, "COMPLETED")
        self.assertEqual(rebuilt_trees_item.status, "PLANNED")

    @mock.patch("apps.courses.views.generate_schedule_from_course")
    @mock.patch(
        "apps.courses.views.index_course_materials",
        return_value={
            "status": "SUCCESS",
            "topics": ["Arrays", "Linked Lists"],
            "num_chunks": 2,
            "embedding_backend": "hash-fallback",
        },
    )
    def test_upload_uses_fast_schedule_generation_mode(self, _mock_index, mock_generate_schedule):
        mock_generate_schedule.return_value = [
            {
                "class_number": 1,
                "topic": "Arrays",
                "subtopics": ["Array traversal"],
                "learning_objectives": ["Explain array traversal."],
                "duration_minutes": 60,
            },
            {
                "class_number": 2,
                "topic": "Linked Lists",
                "subtopics": ["Node structure"],
                "learning_objectives": ["Explain node links."],
                "duration_minutes": 60,
            },
        ]

        response = self.client.post(
            reverse("course-syllabus", args=[self.course.id]),
            {
                "title": "Week 1 Notes",
                "syllabus_text": "Week 1: Arrays. Week 2: Linked lists. Late submissions lose 10% per day.",
            },
        )

        self.assertEqual(response.status_code, 200)
        mock_generate_schedule.assert_called_once()
        self.assertFalse(mock_generate_schedule.call_args.kwargs["use_ai"])
        self.assertFalse(self.course.schedule_items.first().is_ai_generated)

    @mock.patch("apps.courses.views.generate_schedule_from_course")
    def test_schedule_generate_endpoint_uses_ai_mode(self, mock_generate_schedule):
        self.course.materials.create(
            title="Week 1 Notes",
            content_text="Week 1: Arrays. Week 2: Linked lists.",
            extracted_topics=["Arrays", "Linked Lists"],
            parse_status=ParseStatus.SUCCESS,
        )
        mock_generate_schedule.return_value = [
            {
                "class_number": 1,
                "topic": "Arrays",
                "subtopics": ["Array traversal"],
                "learning_objectives": ["Explain array traversal."],
                "duration_minutes": 60,
            }
        ]

        response = self.client.post(reverse("schedule-generate", args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        mock_generate_schedule.assert_called_once()
        self.assertTrue(mock_generate_schedule.call_args.kwargs["use_ai"])
        self.course.refresh_from_db()
        self.assertTrue(self.course.schedule_items.first().is_ai_generated)
