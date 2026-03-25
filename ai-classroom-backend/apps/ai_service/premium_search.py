"""
Premium semantic search with multi-strategy retrieval for better accuracy.
Uses query expansion, hybrid search, and intelligent ranking.
"""
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
import re
from django.core.cache import cache
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with metadata."""
    text: str
    material_id: int
    page_num: int
    relevance_score: float
    retrieval_method: str  # 'semantic', 'lexical', 'heading', 'hybrid'
    keyword_matches: int = 0
    is_section_heading: bool = False


class QueryProcessor:
    """Pre-process queries for better retrieval."""
    
    # Educational synonyms and expansions
    DOMAIN_EXPANSIONS = {
        'concept': ['idea', 'principle', 'theory', 'notion', 'definition'],
        'define': ['meaning', 'explanation', 'definition', 'what'],
        'process': ['method', 'procedure', 'steps', 'mechanism', 'workflow'],
        'explain': ['describe', 'elaborate', 'clarify', 'detail', 'expound'],
        'example': ['instance', 'illustration', 'case', 'sample', 'scenario'],
        'algorithm': ['procedure', 'method', 'approach', 'technique'],
        'data structure': ['structure', 'format', 'organization', 'layout'],
        'function': ['method', 'procedure', 'routine', 'operation'],
        'variable': ['parameter', 'attribute', 'property', 'term'],
    }
    
    STOPWORDS = {
        'what', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but', 'to',
        'of', 'in', 'on', 'at', 'by', 'for', 'from', 'with', 'as',
        'be', 'been', 'being', 'do', 'does', 'did', 'will', 'would',
        'can', 'could', 'should', 'may', 'might', 'must', 'have', 'has', 'had',
    }
    
    def expand_query(self, query: str) -> List[str]:
        """Generate query variations for better retrieval."""
        query_lower = query.lower()
        variations = [query_lower]
        
        # Check for domain-specific terms to expand
        for term, expansions in self.DOMAIN_EXPANSIONS.items():
            if term in query_lower:
                for expansion in expansions:
                    var = query_lower.replace(term, expansion)
                    if var not in variations:
                        variations.append(var)
        
        return variations[:5]  # Limit to 5 variations
    
    def extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query."""
        words = query.lower().split()
        keywords = [
            w for w in words
            if w not in self.STOPWORDS and len(w) > 2 and w.isalpha()
        ]
        return keywords[:8]  # Top 8 keywords
    
    def get_query_intent(self, query: str) -> str:
        """Determine what user is trying to do."""
        query_lower = query.lower()
        
        if any(w in query_lower for w in ['define', 'meaning', 'what is']):
            return 'definition'
        elif any(w in query_lower for w in ['how to', 'how do', 'steps']):
            return 'procedural'
        elif any(w in query_lower for w in ['when', 'where', 'who', 'list', 'name']):
            return 'factual'
        elif any(w in query_lower for w in ['why', 'compare', 'analyze', 'discuss']):
            return 'analytical'
        else:
            return 'general'


class PremiumSemanticSearch:
    """Advanced semantic search with multiple strategies."""
    
    def __init__(self):
        self.query_processor = QueryProcessor()
        self.cache_timeout = 3600  # 1 hour
    
    def search(
        self,
        query: str,
        semantic_results: List[Tuple[str, float]],
        lexical_search_func=None,
        course_id: int = None,
        top_k: int = 8,
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining multiple strategies.
        
        Args:
            query: User query
            semantic_results: Results from semantic search [(text, score), ...]
            lexical_search_func: Function to perform lexical search
            course_id: Optional course ID for caching
            top_k: Number of results to return
        """
        
        # Check cache first
        if course_id:
            cache_key = f"search_results_{course_id}_{hash(query)}"
            cached = cache.get(cache_key)
            if cached:
                return cached
        
        # Process query
        keywords = self.query_processor.extract_keywords(query)
        query_intent = self.query_processor.get_query_intent(query)
        expanded_queries = self.query_processor.expand_query(query)
        
        # Collect results from multiple sources
        all_results = {}
        
        # 1. Semantic search results
        semantic_results = self._process_semantic_results(
            semantic_results, keywords, query_intent
        )
        for result in semantic_results:
            key = result.text[:100]
            all_results[key] = result
        
        # 2. Lexical search if available
        if lexical_search_func:
            lexical_results = self._perform_lexical_search(
                lexical_search_func, expanded_queries, keywords
            )
            for result in lexical_results:
                key = result.text[:100]
                if key not in all_results:
                    all_results[key] = result
        
        # 3. Re-rank combined results
        ranked_results = self._rerank_results(list(all_results.values()), query, keywords)
        
        # Take top K
        final_results = ranked_results[:top_k]
        
        # Cache results
        if course_id:
            cache.set(cache_key, final_results, self.cache_timeout)
        
        return final_results
    
    def _process_semantic_results(
        self,
        semantic_results: List[Tuple[str, float]],
        keywords: List[str],
        intent: str,
    ) -> List[SearchResult]:
        """Convert semantic search results to SearchResult objects."""
        results = []
        
        for text, score in semantic_results:
            # Count keyword matches in text
            keyword_matches = sum(1 for kw in keywords if kw.lower() in text.lower())
            
            # Boost certain content based on intent
            boost = self._calculate_intent_boost(text, intent)
            adjusted_score = min(score * (1.0 + boost), 1.0)
            
            result = SearchResult(
                text=text,
                material_id=0,  # Would be populated from RAG lookup
                page_num=0,
                relevance_score=adjusted_score,
                retrieval_method='semantic',
                keyword_matches=keyword_matches,
                is_section_heading=self._is_section_heading(text),
            )
            results.append(result)
        
        return results
    
    def _perform_lexical_search(
        self,
        search_func,
        queries: List[str],
        keywords: List[str],
    ) -> List[SearchResult]:
        """Perform lexical (keyword) search as fallback."""
        results = []
        seen_texts = set()
        
        for query in queries:
            try:
                # Call the search function
                lexical_results = search_func(query)
                
                if not lexical_results:
                    continue
                
                for text in lexical_results[:3]:  # Top 3 per query
                    if text in seen_texts:
                        continue
                    seen_texts.add(text)
                    
                    # Calculate keyword match score
                    keyword_matches = sum(1 for kw in keywords if kw.lower() in text.lower())
                    lexical_score = min(keyword_matches / max(len(keywords), 1), 1.0)
                    
                    result = SearchResult(
                        text=text,
                        material_id=0,
                        page_num=0,
                        relevance_score=lexical_score,
                        retrieval_method='lexical',
                        keyword_matches=keyword_matches,
                    )
                    results.append(result)
            except Exception as e:
                logger.warning(f"Lexical search failed for query '{query}': {e}")
        
        return results
    
    def _rerank_results(
        self,
        results: List[SearchResult],
        query: str,
        keywords: List[str],
    ) -> List[SearchResult]:
        """Re-rank results using multiple signals."""
        
        for result in results:
            score = result.relevance_score
            
            # Boost for keyword matches
            keyword_boost = (result.keyword_matches / max(len(keywords), 1)) * 0.3
            
            # Boost for section headings
            heading_boost = 0.2 if result.is_section_heading else 0.0
            
            # Boost for semantic method (generally better)
            method_boost = 0.1 if result.retrieval_method == 'semantic' else 0.0
            
            # Length heuristic (not too short, not too long)
            word_count = len(result.text.split())
            if 50 < word_count < 500:
                length_boost = 0.1
            else:
                length_boost = 0.0
            
            result.relevance_score = min(
                score + keyword_boost + heading_boost + method_boost + length_boost,
                1.0
            )
        
        # Sort by relevance score descending
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return results
    
    @staticmethod
    def _calculate_intent_boost(text: str, intent: str) -> float:
        """Boost scores based on query intent matching."""
        text_lower = text.lower()
        
        if intent == 'definition':
            if any(w in text_lower for w in ['define', 'is a', 'refers to', 'means']):
                return 0.2
        elif intent == 'procedural':
            if any(w in text_lower for w in ['step', 'process', 'follow', 'procedure', 'method']):
                return 0.2
        elif intent == 'factual':
            if text[0].isupper() and len(text.split()) < 20:  # Short, capitalized = likely fact
                return 0.15
        elif intent == 'analytical':
            if any(w in text_lower for w in ['because', 'therefore', 'implies', 'reason', 'result']):
                return 0.2
        
        return 0.0
    
    @staticmethod
    def _is_section_heading(text: str) -> bool:
        """Check if text looks like a section heading."""
        # Section headings are typically short and capitalized
        if len(text) > 100:
            return False
        
        # Check for heading patterns
        patterns = [
            r'^(chapter|module|unit|section|lesson|topic|lecture)\s+\d+',
            r'^[A-Z][A-Z\s]{5,50}$',  # Multiple capital letters
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False


class SmartResultAggregator:
    """Intelligently combine results from multiple sources."""
    
    @staticmethod
    def deduplicate_results(results: List[SearchResult]) -> List[SearchResult]:
        """Remove near-duplicate results."""
        deduplicated = []
        seen_texts = set()
        
        for result in results:
            # Check for exact duplicates
            if result.text in seen_texts:
                continue
            
            # Check for near-duplicates (> 90% similar)
            is_duplicate = False
            for seen in seen_texts:
                similarity = SequenceMatcher(None, result.text, seen).ratio()
                if similarity > 0.9:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(result)
                seen_texts.add(result.text)
        
        return deduplicated
    
    @staticmethod
    def balance_retrieval_methods(results: List[SearchResult]) -> List[SearchResult]:
        """
        Balance results to avoid over-relying on one retrieval method.
        Ensures semantic + lexical + others are mixed.
        """
        by_method = {}
        for result in results:
            method = result.retrieval_method
            if method not in by_method:
                by_method[method] = []
            by_method[method].append(result)
        
        # Take top from each method
        balanced = []
        per_method = max(1, 8 // max(len(by_method), 1))
        
        for results_by_method in by_method.values():
            balanced.extend(results_by_method[:per_method])
        
        # Re-sort by relevance
        balanced.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return balanced


class QueryOptimizer:
    """Optimize queries for better search results."""
    
    @staticmethod
    def optimize_for_search(query: str) -> str:
        """
        Optimize query for search engines.
        Removes noise, emphasizes important terms.
        """
        # Remove filler words
        fillers = [
            'uh', 'um', 'like', 'you know', 'i mean', 'can you', 'could you',
            'please', 'thank you', 'thanks', 'hey', 'hello',
        ]
        
        optimized = query.lower()
        for filler in fillers:
            optimized = re.sub(rf'\b{filler}\b', '', optimized, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        optimized = ' '.join(optimized.split())
        
        # Return original if optimization made it empty
        return optimized if optimized else query
    
    @staticmethod
    def suggest_search_refinements(
        original_query: str,
        search_results: List[SearchResult],
    ) -> Optional[str]:
        """
        Suggest query refinements if results are weak.
        Returns None if results are good, or suggested query if weak.
        """
        if not search_results:
            return None
        
        # Calculate average relevance
        avg_relevance = sum(r.relevance_score for r in search_results) / len(search_results)
        
        # If average is low, suggest refinement
        if avg_relevance < 0.5:
            # Try to extract more specific terms
            words = original_query.split()
            if len(words) > 3:
                # Suggest shorter, more specific query
                return " ".join(words[1:4])
        
        return None
