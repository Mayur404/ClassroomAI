"""
Improved answer generation with better source attribution and answer formatting.
Leverages document structure for more accurate, sourced answers.
"""
import logging
import re
from typing import Optional
from .document_parser import QueryAnalyzer

logger = logging.getLogger(__name__)

class AnswerFormatter:
    """Format answers with proper source attribution and structure."""
    
    def __init__(self):
        self.query_analyzer = QueryAnalyzer()
    
    def format_section_answer(self, question: str, section_content: str, 
                             section_heading: str, full_path: list[str]) -> dict:
        """Format answer for a direct section/heading match."""
        
        # Extract the most relevant sentences from section content
        answer = self._extract_most_relevant_sentences(question, section_content, limit=3)
        
        if not answer:
            answer = section_content[:500]
        
        hierarchy = " > ".join(full_path) if full_path else section_heading
        
        return {
            "answer": f"Found in {hierarchy}:\n\n{answer}",
            "is_section_match": True,
            "section_heading": section_heading,
            "hierarchy": hierarchy,
            "answer_type": "section_direct",
        }
    
    def format_search_based_answer(self, question: str, evidence: list[dict],
                                   retrieved_chunks: list[str]) -> dict:
        """Format answer based on search results."""
        
        # Combine evidence into coherent answer
        evidence_text = "\n\n".join([item["text"] for item in evidence[:3]])
        
        # Build answer prompt for LLM
        prompt = self._build_answer_prompt(question, evidence_text, retrieved_chunks)
        
        return {
            "prompt": prompt,
            "evidence_count": len(evidence),
            "chunk_count": len(retrieved_chunks),
            "answer_type": "search_based",
        }
    
    def format_pdf_grounded_answer(self, question: str, evidence: list[dict]) -> str:
        """Format answer grounded in PDF evidence."""
        
        if not evidence:
            return "I couldn't find that information in the uploaded course materials."
        
        # Build from evidence directly
        answer_parts = ["Based on the course materials:\n"]
        
        for idx, item in enumerate(evidence[:3], 1):
            snippet = item.get("text", "").strip()
            if snippet:
                # Limit snippet length
                if len(snippet) > 300:
                    snippet = snippet[:297] + "..."
                answer_parts.append(f"({idx}) {snippet}")
        
        return "\n\n".join(answer_parts)
    
    def _extract_most_relevant_sentences(self, question: str, text: str, 
                                        limit: int = 3) -> str:
        """Extract most relevant sentences from text."""
        if not text:
            return ""
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        query_keywords = set(self.query_analyzer.get_query_keywords(question))
        
        scored_sentences = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Score by keyword overlap
            sentence_words = set(sentence.lower().split())
            keyword_overlap = len(query_keywords & sentence_words)
            
            # Only include sentences with at least some relevance
            if keyword_overlap > 0 or len(sentences) <= 3:
                scored_sentences.append((keyword_overlap, sentence.strip()))
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[0], reverse=True)
        result_sentences = [s[1] for s in scored_sentences[:limit]]
        
        # Return in original order
        for sentence in sentences:
            if sentence.strip() in result_sentences:
                return " ".join([s.strip() for s in sentences 
                               if s.strip() in result_sentences])
        
        return " ".join(result_sentences)
    
    def _build_answer_prompt(self, question: str, evidence: str, 
                            chunks: list[str]) -> str:
        """Build optimized prompt for answer generation."""
        
        context = "\n---\n".join(chunks) if chunks else "No context available."
        
        return f"""You are an expert course tutor. Answer the student's question using ONLY the provided evidence and context from course materials.

IMPORTANT RULES:
1. Use exact quotes or paraphrases from the course evidence
2. If you see a direct match or exact section, reference it
3. Do not add outside knowledge or generic explanations
4. Keep answers concise but complete
5. If the answer cannot be found, say: "I couldn't find this specific information in the course materials."

STUDENT QUESTION:
{question}

EVIDENCE FROM COURSE MATERIALS:
{evidence}

ADDITIONAL CONTEXT:
{context}

ANSWER:"""


class QuestionPreprocessor:
    """Preprocess questions for better understanding and routing."""
    
    FACTUAL_QUESTION_PATTERNS = [
        r"what\s+(?:is|are|was)",
        r"when\s+(?:is|are|was)",
        r"where\s+(?:is|are|was)",
        r"who\s+(?:is|are)",
        r"how many|how much",
        r"define\s+",
        r"explain\s+",
        r"list\s+",
        r"name the",
    ]
    
    CONCEPTUAL_PATTERNS = [
        r"why\s+",
        r"how\s+(?:does|do|can)",
        r"compare|contrast",
        r"relationship\s+between",
    ]
    
    def __init__(self):
        self.factual_patterns = [re.compile(p, re.IGNORECASE) for p in self.FACTUAL_QUESTION_PATTERNS]
        self.conceptual_patterns = [re.compile(p, re.IGNORECASE) for p in self.CONCEPTUAL_PATTERNS]
    
    def classify_question(self, question: str) -> str:
        """Classify question type."""
        question_lower = question.lower()
        
        # Check for factual questions
        for pattern in self.factual_patterns:
            if pattern.search(question_lower):
                return "factual"
        
        # Check for conceptual questions
        for pattern in self.conceptual_patterns:
            if pattern.search(question_lower):
                return "conceptual"
        
        return "general"
    
    def estimate_answer_length(self, question: str) -> int:
        """Estimate answer length needed."""
        question_lower = question.lower()
        
        # List questions need more content
        if "list" in question_lower:
            return 400
        
        # Define/explain questions need moderate
        if "define" in question_lower or "explain" in question_lower:
            return 300
        
        # Yes/no questions need less
        if question.strip().endswith("?") and len(question.split()) <= 10:
            return 150
        
        return 250
    
    def get_search_keywords(self, question: str) -> list[str]:
        """Extract optimal search keywords from question."""
        analyzer = QueryAnalyzer()
        
        # Get base keywords
        keywords = analyzer.get_query_keywords(question)
        
        # Add important noun phrases
        # Look for capitalized terms or quoted terms
        quoted = re.findall(r'"([^"]+)"', question)
        if quoted:
            keywords.extend(quoted)
        
        # Look for capitalized terms (proper nouns, concepts)
        capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', question)
        keywords.extend([c.lower() for c in capitalized])
        
        return list(set(keywords))[:8]


def classify_and_preprocess(question: str) -> dict:
    """Comprehensive question preprocessing."""
    preprocessor = QuestionPreprocessor()
    
    return {
        "original_question": question,
        "question_type": preprocessor.classify_question(question),
        "estimated_answer_length": preprocessor.estimate_answer_length(question),
        "search_keywords": preprocessor.get_search_keywords(question),
    }
