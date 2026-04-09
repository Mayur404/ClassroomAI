"""
Premium answer generation pipeline - integrating all improvements.
Handles PDF extraction, semantic search, source tracking, and grounded prompting.
"""
import logging
import json
from typing import Optional, List, Tuple
import time
from django.core.cache import cache

from .premium_pdf_extraction import PremiumPDFExtractor
from .source_attribution import SourceAttributionManager, RetrievedEvidence
from .premium_prompts import QuestionAnalyzer, PremiumPromptBuilder, ResponseValidator
from .premium_search import PremiumSemanticSearch, QueryProcessor, SmartResultAggregator

logger = logging.getLogger(__name__)


class PremiumAnswerEngine:
    """
    Complete answer generation pipeline with all enhancements.
    - Better PDF extraction (scanned + native)
    - Perfect source attribution
    - Reliable prompting (non-random answers)
    - Better semantic search
    """
    
    def __init__(self):
        self.pdf_extractor = PremiumPDFExtractor()
        self.source_manager = SourceAttributionManager()
        self.query_analyzer = QuestionAnalyzer()
        self.prompt_builder = PremiumPromptBuilder()
        self.response_validator = ResponseValidator()
        self.semantic_searcher = PremiumSemanticSearch()
        self.query_processor = QueryProcessor()
        self.result_aggregator = SmartResultAggregator()
        
        self.response_cache_timeout = 300  # 5 minutes
    
    def answer_question_premium(
        self,
        question: str,
        course,
        user=None,
        search_func=None,
        llm_func=None,
        conversation_history: Optional[List[str]] = None,
    ) -> dict:
        """
        Generate a premium answer with all enhancements.
        
        Returns dict with:
        - answer: The response text
        - sources: Detailed source citations
        - confidence: Overall confidence score
        - metadata: Extraction and processing details
        """
        
        start_time = time.time()
        
        # ===== STEP 1: ANALYZE QUESTION =====
        logger.info(f"Analyzing question: {question[:60]}...")
        analysis = self.query_analyzer.analyze(question, conversation_history)
        
        # ===== STEP 2: PROCESS QUERY =====
        logger.info("Processing query for optimal search...")
        processed_query = self.query_processor.expand_query(question)[0]
        keywords = self.query_processor.extract_keywords(question)
        
        # ===== STEP 3: RETRIEVE EVIDENCE =====
        logger.info("Retrieving evidence from course materials...")
        evidence_list = self._retrieve_evidence(
            question, processed_query, course, search_func
        )
        
        if not evidence_list:
            return self._handle_no_evidence(question, course)
        
        # ===== STEP 4: BUILD OPTIMIZED PROMPT =====
        logger.info("Building optimized prompt...")
        evidence_texts = [ev.text for ev in evidence_list]
        prompt = self.prompt_builder.build_answer_prompt(
            question=question,
            evidence_chunks=evidence_texts,
            analysis=analysis,
            course_name=course.name,
            conversation_history=conversation_history,
        )
        
        # ===== STEP 5: GENERATE ANSWER =====
        logger.info("Generating answer with LLM...")
        if llm_func is None:
            answer_text = self._generate_fallback_answer(evidence_list, question)
        else:
            try:
                answer_text = llm_func(prompt)
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                answer_text = self._generate_fallback_answer(evidence_list, question)
        
        # ===== STEP 6: VALIDATE RESPONSE =====
        logger.info("Validating response quality...")
        is_valid, validation_msg, confidence = self.response_validator.validate_answer(
            answer_text, question, evidence_texts, analysis
        )
        
        if not is_valid:
            logger.warning(f"Response validation failed: {validation_msg}")
            answer_text = self._regenerate_with_fallback(evidence_list, question, answer_text)
        
        # ===== STEP 7: FORMAT ANSWER WITH SOURCES =====
        logger.info("Formatting answer with sources...")
        formatted_answer = self.source_manager.format_answer_with_sources(
            answer_text, evidence_list
        )
        
        # ===== STEP 8: BUILD RESPONSE =====
        processing_time_ms = (time.time() - start_time) * 1000
        
        response = {
            "answer": formatted_answer["answer"],
            "sources": formatted_answer["sources"],
            "confidence": max(confidence, 0.0),
            "has_scanned_documents": formatted_answer["has_scanned_documents"],
            "metadata": {
                "question_type": analysis.question_type,
                "difficulty_level": analysis.difficulty_level,
                "processing_time_ms": processing_time_ms,
                "evidence_count": len(evidence_list),
                "is_valid": is_valid,
                "validation_message": validation_msg,
            }
        }
        
        logger.info(f"Answer generation complete in {processing_time_ms:.0f}ms "
                   f"(confidence: {confidence:.0%})")
        
        return response
    
    def _retrieve_evidence(
        self,
        question: str,
        processed_query: str,
        course,
        search_func,
    ) -> List[RetrievedEvidence]:
        """Retrieve evidence using multiple search strategies."""
        
        evidence_list = []
        
        try:
            # Primary: Use provided search function
            if search_func:
                search_results = search_func(processed_query, top_k=10)
            else:
                logger.warning("No search function provided")
                search_results = []
            
            # Convert search results to evidence with source tracking
            for i, (text, score) in enumerate(search_results[:8]):
                evidence = self.source_manager.create_evidence(
                    text=text,
                    source=self.source_manager.track_source(
                        text_chunk=text,
                        material_id=0,  # Would be populated by search function
                        material_name="Course Material",
                        page_num=i,
                        confidence=score,
                    ),
                    relevance_score=score,
                    matching_keywords=self.query_processor.extract_keywords(question),
                )
                evidence_list.append(evidence)
            
            # Deduplicate
            evidence_list = self.result_aggregator.deduplicate_results(evidence_list)
            
        except Exception as e:
            logger.error(f"Evidence retrieval failed: {e}")
        
        return evidence_list
    
    def _generate_fallback_answer(
        self,
        evidence_list: List[RetrievedEvidence],
        question: str,
    ) -> str:
        """Generate answer using evidence when LLM is unavailable."""
        
        if not evidence_list:
            return "I couldn't find relevant information in the course materials."
        
        # Use top evidence piece
        best_evidence = max(evidence_list, key=lambda e: e.relevance_score)
        
        # Build simple answer
        answer_text_trunc = best_evidence.text[:800] + "..." if len(best_evidence.text) > 800 else best_evidence.text
        answer = f"Based on the course materials:\n\n{answer_text_trunc}"
        
        if len(evidence_list) > 1:
            answer += f"\n\n(Plus {len(evidence_list)-1} other sources)"
        
        return answer
    
    def _regenerate_with_fallback(
        self,
        evidence_list: List[RetrievedEvidence],
        question: str,
        original_answer: str,
    ) -> str:
        """Regenerate answer if validation fails."""
        
        logger.info("Regenerating answer with fallback strategy...")
        
        # Try to extract core facts from evidence
        facts = []
        for evidence in evidence_list[:3]:
            # Extract first sentence
            sentences = evidence.text.split('.')
            if sentences:
                fact = sentences[0].strip()
                if len(fact) > 20:
                    facts.append(fact)
        
        if facts:
            fallback_answer = "Based on the course materials:\n"
            fallback_answer += "\n".join(f"• {fact}" for fact in facts)
            return fallback_answer
        
        return original_answer
    
    def _handle_no_evidence(self, question: str, course) -> dict:
        """Handle case when no evidence is found."""
        
        return {
            "answer": f"I couldn't find relevant information about '{question}' in the course materials for {course.name}. "
                     f"Please check if the course materials are uploaded or try rephrasing your question.",
            "sources": [],
            "confidence": 0.0,
            "has_scanned_documents": False,
            "metadata": {
                "question_type": "unknown",
                "difficulty_level": "unknown",
                "evidence_count": 0,
                "is_valid": False,
                "validation_message": "No evidence found",
            }
        }


class BatchProcessingOptimizer:
    """Optimize processing for speed and quality."""
    
    def __init__(self):
        self.cache_timeout = 3600  # 1 hour
    
    def should_use_cached_answer(self, question: str, course_id: int) -> bool:
        """Check if we can use a cached answer."""
        cache_key = f"answer_cache_{course_id}_{hash(question)}"
        return cache.get(cache_key) is not None
    
    def get_cached_answer(self, question: str, course_id: int) -> Optional[dict]:
        """Retrieve cached answer."""
        cache_key = f"answer_cache_{course_id}_{hash(question)}"
        return cache.get(cache_key)
    
    def cache_answer(self, question: str, course_id: int, answer: dict):
        """Cache an answer for reuse."""
        cache_key = f"answer_cache_{course_id}_{hash(question)}"
        cache.set(cache_key, answer, self.cache_timeout)
    
    def cache_search_results(
        self,
        query: str,
        course_id: int,
        results: List[Tuple[str, float]],
    ):
        """Cache search results for reuse."""
        cache_key = f"search_cache_{course_id}_{hash(query)}"
        cache.set(cache_key, results, 1800)  # 30 minutes


class PerformanceMonitor:
    """Monitor and log performance metrics."""
    
    def __init__(self):
        self.metrics = {
            'total_questions': 0,
            'total_time_ms': 0,
            'avg_confidence': 0.0,
            'cache_hit_rate': 0.0,
        }
    
    def log_answer(
        self,
        processing_time_ms: float,
        confidence: float,
        evidence_count: int,
        is_cached: bool,
    ):
        """Log metrics for an answer."""
        self.metrics['total_questions'] += 1
        self.metrics['total_time_ms'] += processing_time_ms
        
        # Update average confidence
        old_avg = self.metrics['avg_confidence'] * (self.metrics['total_questions'] - 1)
        self.metrics['avg_confidence'] = (old_avg + confidence) / self.metrics['total_questions']
        
        logger.info(
            f"Answer logged - Time: {processing_time_ms:.0f}ms, "
            f"Confidence: {confidence:.0%}, Evidence: {evidence_count}"
        )
    
    def get_report(self) -> dict:
        """Get performance report."""
        avg_time = (
            self.metrics['total_time_ms'] / self.metrics['total_questions']
            if self.metrics['total_questions'] > 0
            else 0
        )
        
        return {
            "total_questions_processed": self.metrics['total_questions'],
            "average_response_time_ms": avg_time,
            "average_confidence": self.metrics['avg_confidence'],
            "total_processing_time_ms": self.metrics['total_time_ms'],
        }


# Global instance
premium_engine = PremiumAnswerEngine()
batch_optimizer = BatchProcessingOptimizer()
perf_monitor = PerformanceMonitor()
