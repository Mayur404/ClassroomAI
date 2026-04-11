import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings
import requests

from apps.ai_service.rag_service import _hybrid_rank_results, _search_result_cache, search_course
from apps.ai_service.language_service import normalize_language_code, translate_text_with_sarvam_meta
from apps.ai_service.services import (
    _fallback_grading,
    _group_ocr_detections,
    _merge_page_sources,
    _should_run_ocr,
    grade_submission,
)
from apps.ai_service.voice_chat_service import SpeechService, SpeechTranscript, VoiceChatService


class PdfEnhancementHelpersTests(SimpleTestCase):
    def test_group_ocr_detections_merges_words_on_same_line(self):
        lines = _group_ocr_detections([
            (10.0, 10.0, "Neural"),
            (10.0, 80.0, "Networks"),
            (32.0, 10.0, "Backpropagation"),
        ])

        self.assertEqual(lines[0], "Neural Networks")
        self.assertEqual(lines[1], "Backpropagation")

    def test_merge_page_sources_dedupes_same_text_from_multiple_extractors(self):
        merged = _merge_page_sources(
            ["Week 1: Arrays", "Stack operations"],
            ["Week 1: Arrays", "Queue basics"],
        )

        self.assertEqual(merged.count("Week 1: Arrays"), 1)
        self.assertIn("Stack operations", merged)
        self.assertIn("Queue basics", merged)

    def test_should_run_ocr_for_sparse_or_image_heavy_pages(self):
        self.assertTrue(_should_run_ocr([], image_count=0))
        self.assertTrue(_should_run_ocr(["Short page"], image_count=1))
        self.assertFalse(_should_run_ocr([
            "This page already contains enough extracted text to skip OCR enrichment because it has a long paragraph with many words covering definitions examples explanations applications and structured notes for the model to index without needing any extra OCR pass.",
            "It also includes a second long paragraph with additional terminology worked examples retrieval cues revision prompts and summary statements so the page is clearly rich in machine readable text already."
        ], image_count=0))

    def test_should_skip_ocr_for_text_rich_pages_with_decorative_images(self):
        self.assertFalse(_should_run_ocr([
            "This page contains a searchable introduction to neural networks with definitions examples activation functions training workflow and optimization notes that already provide enough machine readable context.",
            "It also includes a second paragraph covering gradient descent regularization loss functions evaluation criteria and troubleshooting advice for model performance."
        ], image_count=1))


class HybridSearchRankingTests(SimpleTestCase):
    def test_hybrid_rank_results_boosts_chunks_seen_by_both_rankers(self):
        ranked = _hybrid_rank_results(
            vector_results=[
                (0.9, "Backpropagation computes gradients"),
                (0.4, "Queues use FIFO ordering"),
            ],
            lexical_results=[
                (1.0, "Backpropagation computes gradients"),
                (0.8, "Stacks use LIFO ordering"),
            ],
            top_k=2,
        )

        self.assertEqual(ranked[0], "Backpropagation computes gradients")
        self.assertEqual(len(ranked), 2)

    def test_search_course_caches_repeated_queries(self):
        _search_result_cache.clear()

        with mock.patch("apps.ai_service.rag_service._vector_search_scored", return_value=[]), mock.patch(
            "apps.ai_service.rag_service._lexical_search_scored",
            return_value=[(1.0, "Recursion solves smaller versions of the same problem.")],
        ) as mock_lexical:
            first = search_course(42, "What is recursion?", top_k=1)
            second = search_course(42, "What is recursion?", top_k=1)

        self.assertEqual(first, second)
        mock_lexical.assert_called_once()


class EssayGradingTests(SimpleTestCase):
    def _essay_assignment(self, marks=20):
        return SimpleNamespace(
            type="ESSAY",
            title="Essay Assignment",
            total_marks=marks,
            rubric=[
                {
                    "question_number": 1,
                    "criteria": [
                        "Explain the main concept accurately.",
                        "Include a relevant example or application.",
                    ],
                }
            ],
            questions=[
                {
                    "question_number": 1,
                    "prompt": "Explain photosynthesis and give one practical example.",
                    "marks": marks,
                }
            ],
            answer_key={},
        )

    @mock.patch("apps.ai_service.services.call_ollama")
    def test_grade_submission_preserves_llm_scores_for_essay_breakdown(self, mock_call_ollama):
        assignment = self._essay_assignment()
        mock_call_ollama.return_value = json.dumps(
            {
                "total_score": 16,
                "score_breakdown": [
                    {
                        "question_number": 1,
                        "score": 16,
                        "max_score": 20,
                        "feedback": "Good understanding with a relevant example.",
                        "student_answer": "Photosynthesis lets plants make food from sunlight.",
                    }
                ],
                "overall_feedback": "Good work overall.",
            }
        )

        result = grade_submission(
            assignment=assignment,
            answers={"1": "Photosynthesis lets plants make food from sunlight and store energy in glucose."},
        )

        self.assertEqual(result["total_score"], 16.0)
        self.assertEqual(result["score_breakdown"][0]["score"], 16.0)
        self.assertEqual(result["score_breakdown"][0]["max_score"], 20.0)
        self.assertIn("Good understanding", result["score_breakdown"][0]["feedback"])

    def test_fallback_grading_stays_moderate_for_short_but_relevant_essay_answers(self):
        assignment = self._essay_assignment(marks=10)

        result = _fallback_grading(
            assignment=assignment,
            answers={"1": "Photosynthesis helps plants make food. For example, leaves use sunlight."},
        )

        self.assertGreaterEqual(result["total_score"], 4.0)
        self.assertLessEqual(result["total_score"], 10.0)
        self.assertIn("relev", result["score_breakdown"][0]["feedback"].lower())

    def test_fallback_grading_penalizes_off_topic_answers(self):
        assignment = self._essay_assignment(marks=10)

        result = _fallback_grading(
            assignment=assignment,
            answers={"1": "Cricket is a sport played between two teams with bats and balls."},
        )

        self.assertLess(result["total_score"], 3.5)
        self.assertTrue(
            any(
                phrase in result["score_breakdown"][0]["feedback"].lower()
                for phrase in ["off-topic", "vague", "incomplete", "limited relevance"]
            )
        )


class VoiceChatServiceTests(SimpleTestCase):
    def test_normalize_language_code_maps_common_aliases(self):
        self.assertEqual(normalize_language_code("hi"), "hi-IN")
        self.assertEqual(normalize_language_code("Hindi"), "hi-IN")
        self.assertEqual(normalize_language_code("ta"), "ta-IN")
        self.assertEqual(normalize_language_code("english"), "en-IN")

    @override_settings(SARVAM_API_KEY="x" * 32)
    @mock.patch("apps.ai_service.language_service.requests.post")
    def test_translate_uses_string_payload_and_string_response(self, mock_post):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "translated_text": "\u092f\u0939 \u090f\u0915 \u0909\u0924\u094d\u0924\u0930 \u0939\u0948\u0964",
            "source_language_code": "en-IN",
        }
        mock_post.return_value = mock_response

        result = translate_text_with_sarvam_meta(
            "This is an answer.",
            source_language_code="en-IN",
            target_language_code="hi-IN",
        )

        self.assertEqual(result["translated_text"], "\u092f\u0939 \u090f\u0915 \u0909\u0924\u094d\u0924\u0930 \u0939\u0948\u0964")
        self.assertTrue(result["used_translation"])
        self.assertEqual(mock_post.call_args.kwargs["json"]["input"], "This is an answer.")

    @override_settings(SARVAM_API_KEY="x" * 32)
    @mock.patch("apps.ai_service.services.call_ollama", return_value="\u092f\u0939 \u0917\u094d\u0930\u094b\u0915 \u0905\u0928\u0941\u0935\u093e\u0926 \u0939\u0948\u0964")
    @mock.patch("apps.ai_service.language_service.requests.post")
    def test_translate_falls_back_to_groq_when_sarvam_rejects_request(self, mock_post, _mock_call_ollama):
        mock_response = mock.Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
        mock_post.return_value = mock_response

        result = translate_text_with_sarvam_meta(
            "This is an answer.",
            source_language_code="en-IN",
            target_language_code="hi-IN",
        )

        self.assertEqual(result["translated_text"], "\u092f\u0939 \u0917\u094d\u0930\u094b\u0915 \u0905\u0928\u0941\u0935\u093e\u0926 \u0939\u0948\u0964")
        self.assertTrue(result["used_translation"])

    @override_settings(SARVAM_API_KEY="x" * 32)
    @mock.patch("apps.ai_service.voice_chat_service.requests.post")
    def test_tts_accepts_audio_list_with_base64_string(self, mock_post):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "audios": ["ZmFrZUF1ZGlv"],
        }
        mock_post.return_value = mock_response

        audio = SpeechService().text_to_speech_with_sarvam(
            text="Hello world",
            target_language_code="en-IN",
            speaker="shubh",
            model="bulbul:v3",
            output_audio_codec="wav",
        )

        self.assertEqual(audio.audio_base64, "ZmFrZUF1ZGlv")
        self.assertEqual(audio.mime_type, "audio/wav")

    @mock.patch("apps.ai_service.voice_chat_service.translate_text_with_sarvam_meta")
    @mock.patch("apps.ai_service.voice_chat_service.answer_pdf_chat_question")
    def test_voice_answer_uses_spoken_language_for_tts(self, mock_answer_pdf_chat_question, mock_translate):
        service = VoiceChatService()
        service.speech = mock.Mock()
        service.speech.transcribe_with_sarvam.side_effect = [
            SpeechTranscript(transcript="\u0928\u092e\u0938\u094d\u0924\u0947", language_code="hi"),
            SpeechTranscript(transcript="hello", language_code="en-IN"),
        ]
        service.speech.text_to_speech_with_sarvam.return_value = mock.Mock(
            audio_base64="ZmFrZQ==",
            mime_type="audio/wav",
        )
        mock_answer_pdf_chat_question.return_value = {
            "answer_text": "This is the answer.",
            "sources": [],
        }
        mock_translate.return_value = {
            "translated_text": "\u092f\u0939 \u0909\u0924\u094d\u0924\u0930 \u0939\u0948\u0964",
            "target_language_code": "hi-IN",
            "used_translation": True,
        }

        result = service.answer_voice_question(course=mock.Mock(id=22), user=mock.Mock(id=1), audio_file=mock.Mock())

        self.assertEqual(result["detected_language_code"], "hi-IN")
        self.assertEqual(result["answer_language_code"], "hi-IN")
        service.speech.text_to_speech_with_sarvam.assert_called_once()
        self.assertEqual(service.speech.text_to_speech_with_sarvam.call_args.kwargs["target_language_code"], "hi-IN")
