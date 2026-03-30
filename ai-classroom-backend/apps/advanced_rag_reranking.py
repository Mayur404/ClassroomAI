"""
Advanced RAG with reranking to improve answer quality.
Uses cross-encoder models to rerank retrieved documents by relevance.
"""
from typing import List, Dict, Any, Tuple
import logging
import time
from dataclasses import dataclass
from sentence_transformers import CrossEncoder
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RankedDocument:
    """Document with ranking score."""
    id: str
    content: str
    score: float  # Original retrieval score (0-1)
    rerank_score: float  # Reranking score (0-1)
    relevance_percentile: int  # Percentile rank relative to other results


class AdvancedRAGReranker:
    """
    Reranks documents using cross-encoder models for better relevance.
    
    Flow:
    1. Retrieve top-K documents via dense search (fast but less accurate)
    2. Rerank with cross-encoder (slow but very accurate)
    3. Return top-P reranked documents
    
    This improves answer quality while maintaining speed.
    """
    
    def __init__(self, 
                 model_name: str = "mixedbread-ai/mxbai-rerank-base-v1",
                 top_k_retrieval: int = 50,
                 top_k_reranked: int = 10,
                 threshold: float = 0.3):
        """
        Initialize reranker.
        
        Args:
            model_name: Cross-encoder model from HuggingFace
            top_k_retrieval: Retrieve this many documents before reranking
            top_k_reranked: Keep this many after reranking
            threshold: Minimum score threshold for results
        """
        self.model_name = model_name
        self.top_k_retrieval = top_k_retrieval
        self.top_k_reranked = top_k_reranked
        self.threshold = threshold
        
        self._reranker = None
        self._load_model()
    
    def _load_model(self):
        """Load cross-encoder model lazily."""
        try:
            logger.info(f"Loading reranking model: {self.model_name}")
            self._reranker = CrossEncoder(self.model_name)
        except Exception as e:
            logger.warning(f"Failed to load reranker model: {e}. Using fallback.")
            self._reranker = None
    
    def rerank(self, 
               query: str, 
               documents: List[Dict[str, Any]]) -> Tuple[List[RankedDocument], Dict]:
        """
        Rerank documents for a query.
        
        Args:
            query: User's query
            documents: List of documents with format:
                      [{"id": str, "content": str, "score": float}, ...]
        
        Returns:
            (reranked_documents, metrics)
        """
        start_time = time.time()
        
        if not documents:
            return [], {"rerank_time_ms": 0, "documents_reranked": 0}
        
        if self._reranker is None:
            logger.warning("Reranker model not loaded, returning original ranking")
            return self._format_results(documents, documents), {
                "rerank_time_ms": 0,
                "documents_reranked": 0,
                "fallback_used": True
            }
        
        # Prepare pairs for cross-encoder
        pairs = [[query, doc["content"]] for doc in documents]
        
        # Get reranking scores
        rerank_scores = self._reranker.predict(pairs)
        
        # Normalize scores to 0-1
        min_score = rerank_scores.min()
        max_score = rerank_scores.max()
        if max_score > min_score:
            normalized_scores = (rerank_scores - min_score) / (max_score - min_score)
        else:
            normalized_scores = np.ones_like(rerank_scores)
        
        # Attach rerank scores and sort
        for i, doc in enumerate(documents):
            doc["rerank_score"] = float(normalized_scores[i])
        
        # Sort by rerank score descending
        sorted_docs = sorted(documents, key=lambda x: x.get("rerank_score", 0), reverse=True)
        
        # Filter by threshold and take top-K
        filtered_docs = [d for d in sorted_docs if d["rerank_score"] >= self.threshold]
        final_docs = filtered_docs[:self.top_k_reranked]
        
        # Calculate percentiles
        results = self._format_results(final_docs, sorted_docs)
        
        rerank_time = (time.time() - start_time) * 1000
        
        return results, {
            "rerank_time_ms": rerank_time,
            "documents_reranked": len(documents),
            "documents_returned": len(results),
            "threshold": self.threshold,
            "avg_rerank_score": float(np.mean([d.rerank_score for d in results])) if results else 0,
            "score_distribution": {
                "min": float(min([d.rerank_score for d in results])) if results else 0,
                "max": float(max([d.rerank_score for d in results])) if results else 0,
            }
        }
    
    def _format_results(self, 
                        final_docs: List[Dict], 
                        all_docs: List[Dict]) -> List[RankedDocument]:
        """Format results with percentile ranking."""
        results = []
        
        for i, doc in enumerate(final_docs):
            # Calculate percentile
            rank_position = next((j for j, d in enumerate(all_docs) 
                                 if d.get("id") == doc.get("id")), len(all_docs))
            percentile = int(100 * (1 - rank_position / len(all_docs)))
            
            result = RankedDocument(
                id=doc["id"],
                content=doc["content"],
                score=doc.get("score", 0.0),
                rerank_score=doc.get("rerank_score", 0.0),
                relevance_percentile=percentile
            )
            results.append(result)
        
        return results


class EnhancedRAGServiceWithReranking:
    """
    RAG service that combines dense retrieval with cross-encoder reranking.
    """
    
    def __init__(self):
        self.reranker = AdvancedRAGReranker()
        logger.info("Enhanced RAG service initialized with reranking")
    
    def retrieve_and_rerank(self,
                           query: str,
                           retriever: Any,  # Your existing retriever
                           top_k_initial: int = 50,
                           top_k_final: int = 10) -> Tuple[List[RankedDocument], Dict]:
        """
        Retrieve documents and rerank them.
        
        Args:
            query: User query
            retriever: Your dense retriever (ChromaDB, etc.)
            top_k_initial: Initial number of documents to retrieve
            top_k_final: Final number after reranking
        
        Returns:
            (reranked_results, metrics)
        """
        start = time.time()
        
        # Step 1: Dense retrieval (fast)
        retrieval_start = time.time()
        raw_results = retriever.query(query, top_k=top_k_initial)
        retrieval_time = (time.time() - retrieval_start) * 1000
        
        # Convert to document format
        documents = [
            {
                "id": result["id"],
                "content": result["text"],
                "score": result.get("distance", 0.0),
                "metadata": result.get("metadata", {})
            }
            for result in raw_results
        ]
        
        # Step 2: Rerank (slower but more accurate)
        reranked, rerank_metrics = self.reranker.rerank(query, documents)
        
        total_time = (time.time() - start) * 1000
        
        metrics = {
            "retrieval_time_ms": retrieval_time,
            "rerank_metrics": rerank_metrics,
            "total_time_ms": total_time,
            "pipeline": "retrieve_and_rerank",
            "final_count": len(reranked),
        }
        
        return reranked, metrics
    
    def get_augmented_context(self,
                              reranked_docs: List[RankedDocument],
                              max_tokens: int = 2000) -> str:
        """
        Prepare augmented context from reranked documents.
        Uses rerank scores to weight importance.
        """
        context_parts = []
        token_count = 0
        
        for i, doc in enumerate(reranked_docs):
            # Prefix with rerank confidence
            prefix = f"[Relevance: {doc.rerank_score:.0%}, Rank: {i+1}]\n"
            content = f"{prefix}{doc.content}\n"
            
            token_count += len(content.split())
            if token_count > max_tokens:
                break
            
            context_parts.append(content)
        
        return "\n---\n".join(context_parts)


class HybridRetrievalStrategy:
    """
    Combines multiple retrieval strategies for better coverage.
    """
    
    def __init__(self):
        self.reranker = AdvancedRAGReranker()
    
    def hybrid_retrieve(self,
                       query: str,
                       dense_retriever: Any,  # ChromaDB
                       sparse_retriever: Any,  # BM25
                       normalize: bool = True) -> List[RankedDocument]:
        """
        Combine dense and sparse retrieval, then rerank.
        
        Dense: Semantic similarity
        Sparse: Keyword matching
        Result: Best of both worlds
        """
        # Dense retrieval
        try:
            dense_results = dense_retriever.query(query, top_k=25)
            dense_docs = [
                {
                    "id": f"dense_{i}",
                    "content": r["text"],
                    "score": r.get("distance", 0.0),
                    "method": "dense"
                }
                for i, r in enumerate(dense_results)
            ]
        except Exception as e:
            logger.warning(f"Dense retrieval failed: {e}")
            dense_docs = []
        
        # Sparse retrieval
        try:
            sparse_results = sparse_retriever.query(query, top_k=25)
            sparse_docs = [
                {
                    "id": f"sparse_{i}",
                    "content": r["text"],
                    "score": r.get("bm25_score", 0.0),
                    "method": "sparse"
                }
                for i, r in enumerate(sparse_results)
            ]
        except Exception as e:
            logger.warning(f"Sparse retrieval failed: {e}")
            sparse_docs = []
        
        # Combine and deduplicate by content
        combined = {}
        for doc in dense_docs + sparse_docs:
            key = doc["content"][:100]  # Use content prefix as key
            if key not in combined:
                combined[key] = doc
            else:
                # Keep both retrieval methods in metadata
                if "methods" not in combined[key]:
                    combined[key]["methods"] = [combined[key]["method"]]
                combined[key]["methods"].append(doc["method"])
        
        documents = list(combined.values())
        
        # Rerank combined results
        reranked, metrics = self.reranker.rerank(query, documents)
        
        logger.info(f"Hybrid retrieval: {len(dense_docs)} dense + {len(sparse_docs)} sparse "
                   f"→ {len(reranked)} reranked")
        
        return reranked
