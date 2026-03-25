"""
Enhanced RAG service with better semantic search, metadata-aware retrieval, and intelligent caching.
Works with existing RAG infrastructure to provide faster, more accurate answers.
"""
import logging
from functools import lru_cache
from typing import Optional
import json

from .document_parser import DocumentStructureParser, QueryAnalyzer, DocumentSection
from .rag_service import search_course as original_search_course
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Cache settings
PARSER_CACHE_TIMEOUT = 3600 * 24  # 24 hours
SECTION_MATCH_CACHE_TIMEOUT = 3600  # 1 hour
RELEVANCE_CACHE_TIMEOUT = 1800  # 30 minutes

class EnhancedRAGService:
    """Enhanced RAG with structure-aware retrieval and intelligent scoring."""
    
    def __init__(self):
        self.query_analyzer = QueryAnalyzer()
        self.parsers: dict[int, DocumentStructureParser] = {}
        self.parser_metadata: dict[int, dict] = {}
    
    def index_with_structure(self, course_id: int, material_id: int, text: str) -> dict:
        """Index material with document structure information."""
        parser = DocumentStructureParser()
        sections = parser.parse(text)
        
        # Cache the parser
        parser_key = f"doc_parser_{course_id}_{material_id}"
        cache.set(parser_key, parser, PARSER_CACHE_TIMEOUT)
        
        metadata = {
            "material_id": material_id,
            "course_id": course_id,
            "section_count": len(sections),
            "sections": [
                {
                    "heading": s.heading,
                    "level": s.level,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "keywords": s.keywords,
                    "full_path": s.full_path,
                }
                for s in sections
            ]
        }
        
        metadata_key = f"doc_metadata_{course_id}_{material_id}"
        cache.set(metadata_key, metadata, PARSER_CACHE_TIMEOUT)
        
        logger.info(f"Indexed material {material_id} with {len(sections)} document sections")
        return {
            "status": "SUCCESS",
            "sections_found": len(sections),
            "section_headings": [s.heading for s in sections[:10]],
        }
    
    def get_parser(self, course_id: int, material_id: int) -> Optional[DocumentStructureParser]:
        """Retrieve cached parser for a material."""
        parser_key = f"doc_parser_{course_id}_{material_id}"
        return cache.get(parser_key)
    
    def intelligent_search(self, course_id: int, question: str, top_k: int = 6) -> dict:
        """Intelligently search using query structure understanding."""
        # Check if this is a section/heading query
        is_heading_query = self.query_analyzer.is_heading_query(question)
        heading_query = self.query_analyzer.extract_heading_query(question) if is_heading_query else None
        query_keywords = self.query_analyzer.get_query_keywords(question)
        
        results = {
            "is_heading_query": is_heading_query,
            "heading_query": heading_query,
            "query_keywords": query_keywords,
            "sections_matched": [],
            "standard_results": [],
        }
        
        # Try to match heading directly
        if is_heading_query and heading_query:
            cache_key = f"section_match_{course_id}_{heading_query}"
            cached_match = cache.get(cache_key)
            
            if cached_match is None:
                # Try to find the heading in each material's parser
                from apps.courses.models import CourseMaterial
                materials = CourseMaterial.objects.filter(course_id=course_id)
                
                for material in materials:
                    parser = self.get_parser(course_id, material.id)
                    if parser and parser.sections:
                        section = parser.find_section_by_heading(heading_query)
                        if section:
                            results["sections_matched"].append({
                                "material_id": material.id,
                                "heading": section.heading,
                                "level": section.level,
                                "full_path": section.full_path,
                                "content_preview": section.content[:500],
                            })
                
                cache.set(cache_key, results["sections_matched"], SECTION_MATCH_CACHE_TIMEOUT)
            else:
                results["sections_matched"] = cached_match
        
        # Fall back to standard semantic/lexical search
        standard_results = original_search_course(course_id, question, top_k=top_k)
        results["standard_results"] = standard_results
        
        return results
    
    def re_rank_by_relevance(self, question: str, search_results: list[str], 
                             sections_matched: list[dict] = None) -> list[tuple[float, str]]:
        """Re-rank search results by computed relevance to question."""
        cache_key = f"rerank_{question[:50]}_{len(search_results)}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        scored_results = []
        query_lower = question.lower()
        query_keywords = set(self.query_analyzer.get_query_keywords(question))
        
        for result in search_results:
            score = 0.0
            result_lower = result.lower()
            
            # Boost exact phrase matches
            if query_lower in result_lower:
                score += 2.0
            
            # Boost keyword matches
            result_words = set(result_lower.split())
            keyword_matches = len(query_keywords & result_words)
            score += keyword_matches * 0.5
            
            # Boost if result looks like it's from a section heading
            if any(result.startswith(c) and 
                   len(result.split()) <= 10 for c in ["Chapter", "Section", "Module", "Lesson"]):
                score += 0.3
            
            # Boost length appropriateness (not too short or too long)
            word_count = len(result.split())
            if 50 <= word_count <= 400:
                score += 0.2
            
            scored_results.append((score, result))
        
        # Sort by score descending
        ranked = sorted(scored_results, key=lambda x: x[0], reverse=True)
        cache.set(cache_key, ranked, RELEVANCE_CACHE_TIMEOUT)
        return ranked


# Global service instance
_enhanced_rag = EnhancedRAGService()

def index_material_with_structure(course_id: int, material_id: int, text: str) -> dict:
    """Public function to index material with document structure."""
    return _enhanced_rag.index_with_structure(course_id, material_id, text)

def intelligent_search(course_id: int, question: str, top_k: int = 6) -> dict:
    """Public function for intelligent search."""
    return _enhanced_rag.intelligent_search(course_id, question, top_k=top_k)

def get_ranked_results(question: str, search_results: list[str], 
                       sections_matched: list[dict] = None) -> list[tuple[float, str]]:
    """Public function to re-rank results by relevance."""
    return _enhanced_rag.re_rank_by_relevance(question, search_results, sections_matched)
