"""
Premium source attribution system for perfect tracking of PDF sources.
Enables exact referencing: page numbers, section paths, confidence scores.
"""
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List
from datetime import datetime
import json
from django.core.cache import cache
from django.db import models

logger = logging.getLogger(__name__)


@dataclass
class SourceLocation:
    """Precise location of a source in a PDF."""
    material_id: int
    material_name: str
    page_number: int
    section_path: Optional[List[str]] = None  # e.g., ["Chapter 1", "Section 1.2"]
    paragraph_index: int = 0
    confidence: float = 1.0
    extraction_method: str = "native"  # "native", "ocr_native", "ocr_scanned"
    is_scanned: bool = False
    
    def to_dict(self):
        return asdict(self)
    
    def format_display(self) -> str:
        """Format for display to users."""
        parts = []
        
        # Material name
        parts.append(f"📄 {self.material_name}")
        
        # Page reference
        parts.append(f"Page {self.page_number}")
        
        # Section path
        if self.section_path:
            section_text = " → ".join(self.section_path)
            parts.append(section_text)
        
        # OCR indicator
        if self.is_scanned:
            parts.append("🔍 Scanned Document")
        elif self.extraction_method.startswith("ocr"):
            parts.append("🔍 OCR-Extracted")
        
        # Confidence indicator
        if self.confidence < 0.85:
            parts.append(f"⚠️ ({self.confidence:.0%} confidence)")
        
        return " | ".join(parts)


@dataclass
class RetrievedEvidence:
    """A piece of evidence retrieved from the course materials."""
    text: str
    source: SourceLocation
    relevance_score: float = 0.0
    snippet_index: int = 0
    matching_keywords: List[str] = None
    
    def to_dict(self):
        return {
            "text": self.text,
            "source": self.source.to_dict(),
            "relevance_score": self.relevance_score,
            "snippet_index": self.snippet_index,
            "matching_keywords": self.matching_keywords or [],
        }


class SourceAttributionManager:
    """
    Manage and track sources for all extracted information.
    Ensures every answer can be traced back to original PDF.
    """
    
    def __init__(self):
        self.evidence_cache_timeout = 3600  # 1 hour
        
    def track_source(
        self,
        text_chunk: str,
        material_id: int,
        material_name: str,
        page_num: int,
        section_path: Optional[List[str]] = None,
        confidence: float = 1.0,
        extraction_method: str = "native",
        is_scanned: bool = False,
    ) -> SourceLocation:
        """Create and cache a source location."""
        source = SourceLocation(
            material_id=material_id,
            material_name=material_name,
            page_number=page_num,
            section_path=section_path,
            confidence=confidence,
            extraction_method=extraction_method,
            is_scanned=is_scanned,
        )
        return source
    
    def create_evidence(
        self,
        text: str,
        source: SourceLocation,
        relevance_score: float = 0.0,
        matching_keywords: Optional[List[str]] = None,
    ) -> RetrievedEvidence:
        """Create evidence object with full source tracking."""
        return RetrievedEvidence(
            text=text,
            source=source,
            relevance_score=relevance_score,
            matching_keywords=matching_keywords or [],
        )
    
    def cache_evidence_chunk(
        self,
        course_id: int,
        material_id: int,
        page_num: int,
        text_chunk: str,
        source: SourceLocation,
    ) -> str:
        """Cache evidence chunk for fast retrieval."""
        cache_key = f"source_evidence_{course_id}_{material_id}_{page_num}"
        evidence_data = {
            "text": text_chunk,
            "source": source.to_dict(),
            "cached_at": datetime.now().isoformat(),
        }
        cache.set(cache_key, evidence_data, self.evidence_cache_timeout)
        return cache_key
    
    def get_cached_evidence(
        self,
        course_id: int,
        material_id: int,
        page_num: int,
    ) -> Optional[dict]:
        """Retrieve cached evidence chunk."""
        cache_key = f"source_evidence_{course_id}_{material_id}_{page_num}"
        return cache.get(cache_key)
    
    def merge_overlapping_sources(
        self,
        sources: List[SourceLocation],
        merge_threshold: float = 0.95,
    ) -> List[SourceLocation]:
        """
        Merge sources when multiple chunks point to same location.
        Prevents duplicate citations.
        """
        if not sources:
            return []
        
        merged = []
        used_indices = set()
        
        for i, source1 in enumerate(sources):
            if i in used_indices:
                continue
            
            # Find all similar sources
            similar = [source1]
            
            for j, source2 in enumerate(sources[i+1:], start=i+1):
                if j in used_indices:
                    continue
                
                if self._sources_are_similar(source1, source2, merge_threshold):
                    similar.append(source2)
                    used_indices.add(j)
            
            # Keep the highest confidence version
            best = max(similar, key=lambda s: s.confidence)
            merged.append(best)
            used_indices.add(i)
        
        return merged
    
    @staticmethod
    def _sources_are_similar(
        s1: SourceLocation,
        s2: SourceLocation,
        threshold: float,
    ) -> bool:
        """Check if two sources refer to the same location."""
        # Same material and page
        if s1.material_id != s2.material_id or s1.page_number != s2.page_number:
            return False
        
        # Same section path
        if s1.section_path != s2.section_path:
            return False
        
        # Close enough paragraph index (within 1)
        return abs(s1.paragraph_index - s2.paragraph_index) <= 1
    
    def format_answer_with_sources(
        self,
        answer: str,
        evidence_list: List[RetrievedEvidence],
    ) -> dict:
        """Format answer with proper source citations."""
        # Merge overlapping sources
        sources = [ev.source for ev in evidence_list]
        unique_sources = self.merge_overlapping_sources(sources)
        
        # Group evidence by source
        grouped_evidence = self._group_evidence_by_source(evidence_list)
        
        return {
            "answer": answer,
            "sources": [
                {
                    "location": src.to_dict(),
                    "display": src.format_display(),
                    "evidence_count": len(grouped_evidence.get(src.material_id, [])),
                }
                for src in unique_sources
            ],
            "total_sources": len(unique_sources),
            "average_confidence": (
                sum(src.confidence for src in unique_sources) / len(unique_sources)
                if unique_sources else 0.0
            ),
            "has_scanned_documents": any(src.is_scanned for src in unique_sources),
        }
    
    @staticmethod
    def _group_evidence_by_source(evidence_list: List[RetrievedEvidence]) -> dict:
        """Group evidence chunks by their source material."""
        grouped = {}
        for ev in evidence_list:
            key = ev.source.material_id
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(ev)
        return grouped
    
    def validate_sources(
        self,
        evidence_list: List[RetrievedEvidence],
        min_confidence: float = 0.7,
    ) -> tuple[bool, str]:
        """
        Validate that sources are trustworthy.
        Returns (is_valid, message)
        """
        if not evidence_list:
            return False, "No evidence provided"
        
        sources = [ev.source for ev in evidence_list]
        
        # Check minimum confidence
        low_confidence = [s for s in sources if s.confidence < min_confidence]
        if low_confidence:
            return (
                False,
                f"Some evidence has low confidence: {len(low_confidence)} sources < {min_confidence:.0%}"
            )
        
        # Check for scanned documents (generally lower quality)
        scanned_count = sum(1 for s in sources if s.is_scanned)
        if scanned_count == len(sources) and len(sources) == 1:
            return (
                True,
                f"Using single scanned document"
            )
        
        return True, "Sources validated"
    
    def create_source_context_for_prompt(
        self,
        evidence_list: List[RetrievedEvidence],
    ) -> str:
        """
        Create a context string for the prompt that helps model reference sources.
        """
        if not evidence_list:
            return "No source materials provided."
        
        lines = ["SOURCES:"]
        
        unique_sources = self.merge_overlapping_sources([ev.source for ev in evidence_list])
        
        for i, source in enumerate(unique_sources, 1):
            loc_str = source.format_display()
            lines.append(f"  [{i}] {loc_str}")
        
        lines.append("")
        lines.append("EVIDENCE QUOTES:")
        
        for i, evidence in enumerate(evidence_list[:5], 1):  # Limit to top 5
            lines.append(f"  [{i}] {evidence.text[:200]}...")
        
        return "\n".join(lines)
    
    def generate_confidence_disclaimer(
        self,
        sources: List[SourceLocation],
    ) -> str:
        """Generate a disclaimer if sources aren't fully reliable."""
        if not sources:
            return ""
        
        disclaimers = []
        
        # Check for OCR extraction
        ocr_sources = [s for s in sources if s.extraction_method.startswith("ocr")]
        if ocr_sources:
            disclaimers.append(f"Some content was extracted via OCR ({len(ocr_sources)} sources)")
        
        # Check for low confidence
        low_conf = [s for s in sources if s.confidence < 0.85]
        if low_conf:
            disclaimers.append(f"Some sources have lower confidence ({len(low_conf)} sources)")
        
        if not disclaimers:
            return ""
        
        return "⚠️ " + "; ".join(disclaimers)


class SourceFootprint:
    """Complete footprint of a source document for deduplication."""
    
    def __init__(self, material_id: int, material_name: str, page_num: int):
        self.material_id = material_id
        self.material_name = material_name
        self.page_num = page_num
    
    def __hash__(self):
        return hash((self.material_id, self.page_num))
    
    def __eq__(self, other):
        if not isinstance(other, SourceFootprint):
            return False
        return (
            self.material_id == other.material_id
            and self.page_num == other.page_num
        )


class SourceDeduplicator:
    """Remove duplicate sources from answers."""
    
    @staticmethod
    def deduplicate_evidence(
        evidence_list: List[RetrievedEvidence],
    ) -> List[RetrievedEvidence]:
        """Keep only unique sources, preferring higher relevance."""
        seen = {}
        
        for evidence in evidence_list:
            footprint = SourceFootprint(
                evidence.source.material_id,
                evidence.source.material_name,
                evidence.source.page_number,
            )
            
            if footprint not in seen or evidence.relevance_score > seen[footprint].relevance_score:
                seen[footprint] = evidence
        
        return list(seen.values())
