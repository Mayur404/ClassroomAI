from unittest import mock

from django.test import SimpleTestCase

from apps.ai_service.rag_service import _hybrid_rank_results, _search_result_cache, search_course
from apps.ai_service.services import _group_ocr_detections, _merge_page_sources, _should_run_ocr


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
