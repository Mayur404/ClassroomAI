"""
Advanced document structure parser for better section detection and answering.
Extracts document hierarchy, headings, and enables finding exact sections quickly.
"""
import re
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

HEADING_LEVEL_1 = re.compile(
    r"^(chapter|module|unit|part|section)\s+\d+[a-z]?\s*[:\-\.]*\s*(.+?)$",
    re.IGNORECASE | re.MULTILINE
)
HEADING_LEVEL_2 = re.compile(
    r"^(lesson|topic|lecture|class|session)\s+\d+[a-z]?\s*[:\-\.]*\s*(.+?)$",
    re.IGNORECASE | re.MULTILINE
)
HEADING_LEVEL_3 = re.compile(
    r"^[\d\-\.a-z]*\s*([A-Z][A-Za-z\s]{5,60})$",
    re.MULTILINE
)
HEADING_CAPS = re.compile(r"^[A-Z][A-Z\s\-]{5,80}$", re.MULTILINE)

@dataclass
class DocumentSection:
    """Represents a section in a document with hierarchy."""
    heading: str
    level: int  # 1=chapter, 2=section, 3=subsection
    content: str
    start_line: int
    end_line: int
    keywords: list[str]
    full_path: list[str]  # e.g., ["Chapter 1", "Section 2.1", "Subsection 2.1.3"]
    
    def get_context_window(self, lines: list[str], window_size: int = 200) -> str:
        """Get surrounding context around this section."""
        context_lines = lines[max(0, self.start_line-50):min(len(lines), self.end_line+window_size)]
        return "\n".join(context_lines)


class DocumentStructureParser:
    """Parse and understand document hierarchy for better retrieval."""
    
    def __init__(self):
        self.sections: list[DocumentSection] = []
        self.heading_index: dict[str, DocumentSection] = {}
        self.keyword_to_sections: dict[str, list[DocumentSection]] = {}
        
    def parse(self, text: str) -> list[DocumentSection]:
        """Parse document and extract hierarchical structure."""
        lines = text.split("\n")
        self.sections = []
        self.heading_index = {}
        self.keyword_to_sections = {}
        
        current_level_1 = None
        current_level_2 = None
        current_level_3 = None
        section_content_start = 0
        
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
                
            # Detect level 1 (chapters, modules)
            match_l1 = HEADING_LEVEL_1.match(stripped)
            if match_l1:
                if current_level_3:
                    self._finalize_section(current_level_3, line_num, lines, section_content_start)
                if current_level_2:
                    self._finalize_section(current_level_2, line_num, lines, section_content_start)
                if current_level_1:
                    self._finalize_section(current_level_1, line_num, lines, section_content_start)
                
                heading_text = match_l1.group(2).strip()
                current_level_1 = DocumentSection(
                    heading=heading_text,
                    level=1,
                    content="",
                    start_line=line_num,
                    end_line=line_num,
                    keywords=self._extract_keywords(heading_text),
                    full_path=[heading_text]
                )
                current_level_2 = None
                current_level_3 = None
                section_content_start = line_num
                continue
            
            # Detect level 2 (sections, lectures)
            match_l2 = HEADING_LEVEL_2.match(stripped)
            if match_l2:
                if current_level_3:
                    self._finalize_section(current_level_3, line_num, lines, section_content_start)
                if current_level_2:
                    self._finalize_section(current_level_2, line_num, lines, section_content_start)
                    
                heading_text = match_l2.group(2).strip()
                full_path = [current_level_1.heading] if current_level_1 else []
                full_path.append(heading_text)
                
                current_level_2 = DocumentSection(
                    heading=heading_text,
                    level=2,
                    content="",
                    start_line=line_num,
                    end_line=line_num,
                    keywords=self._extract_keywords(heading_text),
                    full_path=full_path
                )
                current_level_3 = None
                section_content_start = line_num
                continue
            
            # Detect level 3 (subsections)
            if self._is_heading_level_3(stripped):
                if current_level_3:
                    self._finalize_section(current_level_3, line_num, lines, section_content_start)
                    
                full_path = []
                if current_level_1:
                    full_path.append(current_level_1.heading)
                if current_level_2:
                    full_path.append(current_level_2.heading)
                full_path.append(stripped)
                
                current_level_3 = DocumentSection(
                    heading=stripped,
                    level=3,
                    content="",
                    start_line=line_num,
                    end_line=line_num,
                    keywords=self._extract_keywords(stripped),
                    full_path=full_path
                )
                section_content_start = line_num
                
        # Finalize last sections
        for section in [current_level_3, current_level_2, current_level_1]:
            if section:
                self._finalize_section(section, len(lines), lines, section_content_start)
        
        # Build indexes
        for section in self.sections:
            self.heading_index[section.heading.lower()] = section
            for keyword in section.keywords:
                if keyword not in self.keyword_to_sections:
                    self.keyword_to_sections[keyword] = []
                self.keyword_to_sections[keyword].append(section)
        
        logger.info(f"Parsed document: {len(self.sections)} sections found")
        return self.sections
    
    def _is_heading_level_3(self, line: str) -> bool:
        """Check if line is a level 3 heading (subsection)."""
        if len(line) < 6:
            return False
        # All caps or title case
        if HEADING_CAPS.match(line):
            return True
        # Numbered: 2.1.1 Title or (a) Title
        if re.match(r"^[\d\.\-\(\)a-z]+\s+[A-Z]", line):
            return True
        return False
    
    def _extract_keywords(self, text: str, limit: int = 5) -> list[str]:
        """Extract important keywords from heading/section."""
        # Remove common words
        stopwords = {"the", "a", "an", "and", "or", "of", "in", "on", "at", "to", 
                     "for", "is", "are", "was", "be", "by", "with", "as"}
        words = re.findall(r"\b[a-z]{3,}\b", text.lower())
        keywords = [w for w in words if w not in stopwords]
        return keywords[:limit]
    
    def _finalize_section(self, section: DocumentSection, end_line: int, 
                         lines: list[str], content_start: int):
        """Finalize a section with its content."""
        section.end_line = end_line
        section.content = "\n".join(lines[content_start:end_line]).strip()
        if section.content:
            self.sections.append(section)
    
    def find_section_by_heading(self, heading_query: str) -> Optional[DocumentSection]:
        """Find section by exact or fuzzy heading match."""
        query_lower = heading_query.lower().strip()
        
        # Exact match
        if query_lower in self.heading_index:
            return self.heading_index[query_lower]
        
        # Fuzzy match - find section with highest keyword overlap
        query_keywords = set(self._extract_keywords(heading_query))
        if not query_keywords:
            return None
        
        best_match = None
        best_score = 0
        
        for section in self.sections:
            section_keywords = set(section.keywords)
            overlap = len(query_keywords & section_keywords)
            if overlap > best_score:
                best_score = overlap
                best_match = section
        
        return best_match if best_score >= 1 else None
    
    def find_sections_by_keywords(self, keywords: list[str]) -> list[DocumentSection]:
        """Find all sections matching given keywords."""
        results = set()
        for keyword in keywords:
            if keyword in self.keyword_to_sections:
                results.update(self.keyword_to_sections[keyword])
        return list(results)
    
    def get_section_hierarchy(self, section: DocumentSection) -> str:
        """Get full hierarchy path as string."""
        return " > ".join(section.full_path)
    
    def get_section_with_context(self, section: DocumentSection, 
                                 lines: list[str], window: int = 300) -> str:
        """Get section with surrounding context."""
        start = max(0, section.start_line - 10)
        end = min(len(lines), section.end_line + window)
        return "\n".join(lines[start:end])


class QueryAnalyzer:
    """Analyze queries to determine if they're heading/section lookups."""
    
    # Patterns for section/heading queries
    SECTION_QUERY_PATTERNS = [
        r"(?:find|show|look for|where|what.*section|what.*chapter|under|in)\s+(.+?)(?:\?|$)",
        r"(?:heading|section|chapter|topic|lecture)\s+(?:called|named|on|about)?\s*(.+?)(?:\?|$)",
        r"^(?:what is|where is|find)?\s*(.+?)\s+(?:section|chapter|heading|topic|lecture)?\s*\?*$",
    ]
    
    HEADING_KEYWORDS = {
        "section", "chapter", "module", "unit", "lesson", "lecture", 
        "topic", "heading", "title", "part", "class", "session"
    }
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.SECTION_QUERY_PATTERNS]
    
    def is_heading_query(self, question: str) -> bool:
        """Detect if query is looking for a section/heading."""
        question_lower = question.lower()
        
        # Check for heading keywords
        for keyword in self.HEADING_KEYWORDS:
            if keyword in question_lower:
                return True
        
        # Check patterns
        for pattern in self.compiled_patterns:
            if pattern.search(question):
                return True
        
        return False
    
    def extract_heading_query(self, question: str) -> Optional[str]:
        """Extract the heading being searched for."""
        for pattern in self.compiled_patterns:
            match = pattern.search(question)
            if match:
                return match.group(1).strip()
        return None
    
    def get_query_keywords(self, question: str) -> list[str]:
        """Extract important keywords from question."""
        stopwords = {"what", "where", "how", "is", "the", "a", "an", "and", "or",
                    "in", "on", "at", "to", "for", "section", "chapter", "heading",
                    "topic", "about", "find", "show", "look", "called", "named"}
        words = re.findall(r"\b[a-z]{2,}\b", question.lower())
        return [w for w in words if w not in stopwords][:5]
