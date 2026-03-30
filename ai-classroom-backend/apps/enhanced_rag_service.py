"""
Enhanced RAG (Retrieval-Augmented Generation) service with performance tracking
and improved answer generation with confidence scoring.
"""
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from document retrieval."""
    text: str
    source: str
    relevance_score: float
    metadata: Dict[str, Any]


@dataclass
class RAGResponse:
    """Response from RAG system."""
    answer: str
    sources: List[RetrievalResult]
    confidence_score: float
    model_used: str
    generation_time_ms: float
    retrieval_time_ms: float
    total_time_ms: float
    cached: bool = False
    quality_metrics: Dict[str, Any] = None


class PerformanceTracker:
    """Tracks RAG system performance metrics."""
    
    def __init__(self):
        self.queries_processed = 0
        self.total_generation_time = 0
        self.total_retrieval_time = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.errors = 0
    
    @property
    def avg_generation_time(self) -> float:
        """Average generation time in ms."""
        return self.total_generation_time / self.queries_processed if self.queries_processed > 0 else 0
    
    @property
    def avg_retrieval_time(self) -> float:
        """Average retrieval time in ms."""
        return self.total_retrieval_time / self.queries_processed if self.queries_processed > 0 else 0
    
    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate percentage."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0
    
    def record_query(self, generation_time_ms: float, retrieval_time_ms: float, cached: bool = False):
        """Record query metrics."""
        self.queries_processed += 1
        self.total_generation_time += generation_time_ms
        self.total_retrieval_time += retrieval_time_ms
        
        if cached:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def record_error(self):
        """Record error."""
        self.errors += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return {
            "queries_processed": self.queries_processed,
            "avg_generation_time_ms": round(self.avg_generation_time, 2),
            "avg_retrieval_time_ms": round(self.avg_retrieval_time, 2),
            "cache_hit_rate": f"{self.cache_hit_rate:.1f}%",
            "total_errors": self.errors,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }


class ConfidenceScorer:
    """Scores confidence of RAG answers."""
    
    @staticmethod
    def score_answer(
        answer: str,
        sources: List[RetrievalResult],
        relevance_threshold: float = 0.5,
    ) -> float:
        """
        Calculate confidence score for answer (0-100).
        
        Factors:
        - Number and quality of sources
        - Relevance scores of sources
        - Answer length and completeness
        - Source agreement
        """
        confidence = 50  # Base confidence
        
        if not sources:
            return 10  # Very low confidence without sources
        
        # Bonus for multiple relevant sources
        relevant_sources = [s for s in sources if s.relevance_score >= relevance_threshold]
        if len(relevant_sources) >= 3:
            confidence += 30
        elif len(relevant_sources) >= 2:
            confidence += 15
        elif len(relevant_sources) >= 1:
            confidence += 5
        
        # Average relevance score bonus
        avg_relevance = sum(s.relevance_score for s in sources) / len(sources) if sources else 0
        confidence += min(20, int(avg_relevance * 20))
        
        # Answer completeness (longer, more detailed answers)
        word_count = len(answer.split())
        if word_count >= 200:
            confidence += 15
        elif word_count >= 100:
            confidence += 10
        elif word_count >= 50:
            confidence += 5
        
        # Ensure score is between 0-100
        return min(100, max(0, confidence))
    
    @staticmethod
    def score_source(
        relevance_score: float,
        source_length: int = 0,
        model_reliability: float = 0.9,
    ) -> float:
        """Score reliability of individual source."""
        score = relevance_score * 100
        
        # Longer sources are generally more reliable
        if source_length > 1000:
            score += 10
        elif source_length > 500:
            score += 5
        
        # Model reliability factor
        score = score * model_reliability
        
        return min(100, score)


class EnhancedRAGService:
    """
    Enhanced RAG service with performance tracking and confidence scoring.
    """
    
    def __init__(self, cache_service=None, model_provider=None):
        """
        Initialize RAG service.
        
        Args:
            cache_service: Optional caching service
            model_provider: LLM provider (Ollama, Gemini, etc.)
        """
        self.cache_service = cache_service
        self.model_provider = model_provider
        self.performance_tracker = PerformanceTracker()
        self.confidence_scorer = ConfidenceScorer()
    
    def generate_answer(
        self,
        query: str,
        sources: List[RetrievalResult],
        model: str = "qwen2.5:7b",
        temperature: float = 0.7,
        max_tokens: int = 500,
        use_cache: bool = True,
    ) -> RAGResponse:
        """
        Generate answer from query and sources.
        
        Args:
            query: User's question
            sources: Retrieved sources
            model: Model to use
            temperature: Generation temperature
            max_tokens: Max tokens to generate
            use_cache: Use cache if available
            
        Returns:
            RAGResponse with answer, sources, and metrics
        """
        start_time = time.time()
        cached = False
        
        # Check cache
        if use_cache and self.cache_service:
            from apps.cache_utils import CacheKeyBuilder
            cache_key = CacheKeyBuilder.answer_cache(query, len(sources))
            cached_answer = self.cache_service.get(cache_key)
            
            if cached_answer:
                cached = True
                logger.debug("Answer found in cache")
                cached_answer["cached"] = True
                # Record cache hit
                self.performance_tracker.cache_hits += 1
                return cached_answer
        
        self.performance_tracker.cache_misses += 1
        
        # Build prompt with sources
        prompt = self._build_prompt(query, sources)
        
        # Generate answer
        retrieval_time = time.time() - start_time
        generation_start = time.time()
        
        try:
            answer_text = self.model_provider.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ) if self.model_provider else self._default_answer(query, sources)
            
            generation_time = (time.time() - generation_start)
            
            # Calculate confidence
            confidence = self.confidence_scorer.score_answer(answer_text, sources)
            
            # Build quality metrics
            quality_metrics = self._calculate_quality_metrics(
                answer_text, sources, confidence
            )
            
            # Create response
            response = RAGResponse(
                answer=answer_text,
                sources=sources,
                confidence_score=confidence,
                model_used=model,
                generation_time_ms=generation_time * 1000,
                retrieval_time_ms=retrieval_time * 1000,
                total_time_ms=(time.time() - start_time) * 1000,
                cached=cached,
                quality_metrics=quality_metrics,
            )
            
            # Cache the response
            if use_cache and self.cache_service:
                from apps.cache_utils import CacheKeyBuilder
                cache_key = CacheKeyBuilder.answer_cache(query, len(sources))
                self.cache_service.set(cache_key, response, timeout=3600)
            
            # Record metrics
            self.performance_tracker.record_query(
                generation_time * 1000,
                retrieval_time * 1000,
                cached=cached,
            )
            
            logger.info(
                f"Generated answer with confidence {confidence:.1f}% "
                f"({generation_time:.2f}s generation, {retrieval_time:.2f}s retrieval)"
            )
            
            return response
        
        except Exception as e:
            logger.error(f"Failed to generate answer: {str(e)}")
            self.performance_tracker.record_error()
            
            # Return fallback response
            return RAGResponse(
                answer=f"Failed to generate answer: {str(e)}",
                sources=sources,
                confidence_score=0,
                model_used=model,
                generation_time_ms=(time.time() - generation_start) * 1000,
                retrieval_time_ms=retrieval_time * 1000,
                total_time_ms=(time.time() - start_time) * 1000,
                cached=False,
            )
    
    def _build_prompt(self, query: str, sources: List[RetrievalResult]) -> str:
        """Build prompt with sources."""
        prompt_parts = [
            "Based on the following information, answer the question concisely and accurately.",
            "\n\n--- INFORMATION ---\n"
        ]
        
        for i, source in enumerate(sources, 1):
            prompt_parts.append(f"Source {i} ({source.source}):\n{source.text[:1000]}\n")
        
        prompt_parts.extend([
            "\n--- QUESTION ---\n",
            f"{query}\n\n",
            "--- ANSWER ---\n",
            "Provide a clear, concise answer based on the information above."
        ])
        
        return "".join(prompt_parts)
    
    def _default_answer(self, query: str, sources: List[RetrievalResult]) -> str:
        """Fallback answer generation."""
        if sources:
            return f"Based on the retrieved information: {sources[0].text[:200]}..."
        return "Unable to generate answer - no sources available."
    
    def _calculate_quality_metrics(
        self,
        answer: str,
        sources: List[RetrievalResult],
        confidence: float,
    ) -> Dict[str, Any]:
        """Calculate detailed quality metrics."""
        return {
            "answer_length": len(answer),
            "answer_word_count": len(answer.split()),
            "source_count": len(sources),
            "avg_source_relevance": sum(s.relevance_score for s in sources) / len(sources) if sources else 0,
            "confidence_score": confidence,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get service performance metrics."""
        return self.performance_tracker.get_metrics()


# Global RAG service instance
_rag_service = None


def get_rag_service() -> EnhancedRAGService:
    """Get or create global RAG service."""
    global _rag_service
    if _rag_service is None:
        _rag_service = EnhancedRAGService()
    return _rag_service
