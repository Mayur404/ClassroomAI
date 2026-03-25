"""
Premium prompt engineering framework for reliable, grounded answers.
Uses question analysis + source-first approach to prevent hallucination.
"""
import logging
import re
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QuestionAnalysis:
    """Deep analysis of a question to guide answer generation."""
    original_question: str
    question_type: str  # 'definition', 'factual', 'procedural', 'conceptual', 'analytical'
    difficulty_level: str  # 'basic', 'intermediate', 'advanced'
    expected_answer_length: int  # character count
    key_concepts: List[str]
    key_keywords: List[str]
    requires_examples: bool
    requires_explanation: bool
    is_follow_up: bool
    
    def get_instruction_prompt(self) -> str:
        """Get the system instruction based on analysis."""
        instructions = [
            "You are a precise AI tutor. Answer ONLY using provided evidence.",
            f"Question type: {self.question_type.upper()}",
        ]
        
        if self.question_type == 'definition':
            instructions.append("Provide a clear, concise definition from the materials.")
        elif self.question_type == 'factual':
            instructions.append("Find and state the exact facts from the course materials.")
        elif self.question_type == 'procedural':
            instructions.append("Explain the step-by-step procedure as shown in materials.")
        elif self.question_type == 'conceptual':
            instructions.append("Explain the core concept using material references.")
        elif self.question_type == 'analytical':
            instructions.append("Analyze using facts from materials; don't add opinions.")
        
        if self.difficulty_level == 'advanced':
            instructions.append("Go deep; include nuances and edge cases from materials.")
        elif self.difficulty_level == 'basic':
            instructions.append("Keep it simple and straightforward.")
        
        return "\n".join(instructions)


class QuestionAnalyzer:
    """Analyze questions to understand intent and generate better prompts."""
    
    DEFINITION_PATTERNS = [
        r'what\s+(?:is|are|does)\s+',
        r'define\s+',
        r'explain\s+',
        r'what\s+do\s+we\s+mean\s+by',
        r'what\s+is\s+meant\s+by',
    ]
    
    FACTUAL_PATTERNS = [
        r'when\s+',
        r'where\s+',
        r'who\s+',
        r'how\s+many',
        r'how\s+much',
        r'state\s+',
        r'list\s+',
        r'name\s+',
        r'mention\s+',
    ]
    
    PROCEDURAL_PATTERNS = [
        r'how\s+to\s+',
        r'how\s+do\s+',
        r'steps?\s+to\s+',
        r'process\s+of\s+',
        r'method\s+',
        r'procedure\s+',
    ]
    
    ANALYTICAL_PATTERNS = [
        r'compare\s+',
        r'contrast\s+',
        r'analyze\s+',
        r'evaluate\s+',
        r'why\s+',
        r'discuss\s+',
        r'examine\s+',
    ]
    
    def analyze(self, question: str, conversation_history: Optional[List[str]] = None) -> QuestionAnalysis:
        """Perform deep analysis of a question."""
        
        lower_q = question.lower().strip()
        
        # Determine question type
        question_type = self._classify_question_type(lower_q)
        
        # Determine difficulty
        difficulty = self._estimate_difficulty(lower_q)
        
        # Extract key concepts and keywords
        key_concepts = self._extract_key_concepts(lower_q)
        key_keywords = self._extract_keywords(lower_q)
        
        # Estimate answer length based on question type
        expected_length = self._estimate_answer_length(question_type, difficulty)
        
        # Determine what answer should include
        requires_examples = self._question_needs_examples(lower_q)
        requires_explanation = self._question_needs_explanation(lower_q)
        
        # Check if it's a follow-up question
        is_follow_up = conversation_history is not None and len(conversation_history) > 0
        
        return QuestionAnalysis(
            original_question=question,
            question_type=question_type,
            difficulty_level=difficulty,
            expected_answer_length=expected_length,
            key_concepts=key_concepts,
            key_keywords=key_keywords,
            requires_examples=requires_examples,
            requires_explanation=requires_explanation,
            is_follow_up=is_follow_up,
        )
    
    def _classify_question_type(self, question: str) -> str:
        """Classify question type."""
        for pattern in self.PROCEDURAL_PATTERNS:
            if re.search(pattern, question, re.IGNORECASE):
                return 'procedural'
        
        for pattern in self.ANALYTICAL_PATTERNS:
            if re.search(pattern, question, re.IGNORECASE):
                return 'analytical'
        
        for pattern in self.FACTUAL_PATTERNS:
            if re.search(pattern, question, re.IGNORECASE):
                return 'factual'
        
        for pattern in self.DEFINITION_PATTERNS:
            if re.search(pattern, question, re.IGNORECASE):
                return 'definition'
        
        return 'conceptual'
    
    def _estimate_difficulty(self, question: str) -> str:
        """Estimate question difficulty."""
        advanced_words = {
            'advanced', 'complex', 'critically', 'deeply', 'analyze', 'theory',
            'sophisticated', 'nuance', 'implication', 'synthesis', 'evaluate',
        }
        
        basic_words = {
            'simple', 'basic', 'what', 'define', 'list', 'name', 'state',
        }
        
        question_words = set(question.lower().split())
        
        advanced_count = len(question_words & advanced_words)
        basic_count = len(question_words & basic_words)
        
        if advanced_count > basic_count:
            return 'advanced'
        elif basic_count > 0:
            return 'basic'
        else:
            return 'intermediate'
    
    def _extract_key_concepts(self, question: str) -> List[str]:
        """Extract main concepts from question."""
        # Remove stopwords
        stopwords = {
            'what', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but', 'to',
            'of', 'in', 'on', 'at', 'by', 'for', 'from', 'with', 'as', 'can',
            'do', 'does', 'did', 'how', 'when', 'where', 'why', 'which',
        }
        
        tokens = question.lower().split()
        concepts = [t for t in tokens if t not in stopwords and len(t) > 3]
        
        # Take unique, meaningful ones
        return list(dict.fromkeys(concepts))[:5]
    
    def _extract_keywords(self, question: str) -> List[str]:
        """Extract keywords using simple heuristics."""
        # Capital letters (proper nouns) and technical terms
        tokens = question.split()
        keywords = []
        
        for token in tokens:
            # Remove punctuation
            token_clean = re.sub(r'[^\w]', '', token)
            
            if len(token_clean) > 3:
                keywords.append(token_clean.lower())
        
        return list(dict.fromkeys(keywords))[:8]
    
    @staticmethod
    def _estimate_answer_length(question_type: str, difficulty: str) -> int:
        """Estimate appropriate answer length."""
        base_lengths = {
            'definition': 150,
            'factual': 200,
            'procedural': 300,
            'conceptual': 350,
            'analytical': 400,
        }
        
        multipliers = {
            'basic': 0.8,
            'intermediate': 1.0,
            'advanced': 1.5,
        }
        
        base = base_lengths.get(question_type, 250)
        multiplier = multipliers.get(difficulty, 1.0)
        
        return int(base * multiplier)
    
    @staticmethod
    def _question_needs_examples(question: str) -> bool:
        """Check if question should include examples."""
        example_keywords = [
            'example', 'for instance', 'such as', 'like', 'case',
            'illustration', 'instance', 'demonstrate', 'show',
        ]
        lower_q = question.lower()
        return any(kw in lower_q for kw in example_keywords)
    
    @staticmethod
    def _question_needs_explanation(question: str) -> bool:
        """Check if question needs deeper explanation."""
        explanation_keywords = [
            'explain', 'understand', 'how does', 'why', 'reason',
            'cause', 'effect', 'mechanism', 'process', 'work',
        ]
        lower_q = question.lower()
        return any(kw in lower_q for kw in explanation_keywords)


class PremiumPromptBuilder:
    """Build precise, grounded prompts that prevent hallucination."""
    
    def __init__(self):
        self.analyzer = QuestionAnalyzer()
    
    def build_answer_prompt(
        self,
        question: str,
        evidence_chunks: List[str],
        analysis: Optional[QuestionAnalysis] = None,
        course_name: str = "Course",
        conversation_history: Optional[List[str]] = None,
    ) -> str:
        """Build a comprehensive prompt for generating grounded answers."""
        
        if analysis is None:
            analysis = self.analyzer.analyze(question, conversation_history)
        
        prompt_parts = []
        
        # ===== SYSTEM INSTRUCTIONS =====
        prompt_parts.append(self._system_instructions(analysis, course_name))
        
        # ===== EVIDENCE SECTION =====
        if evidence_chunks:
            prompt_parts.append(self._format_evidence_section(evidence_chunks, analysis))
        else:
            prompt_parts.append("EVIDENCE: No relevant course materials found.")
        
        # ===== CONVERSATION CONTEXT =====
        if conversation_history and len(conversation_history) > 0:
            prompt_parts.append(self._format_conversation_context(conversation_history))
        
        # ===== QUESTION =====
        prompt_parts.append(f"QUESTION: {question}")
        
        # ===== ANSWER FORMAT INSTRUCTIONS =====
        prompt_parts.append(self._answer_format_instructions(analysis))
        
        # ===== CRITICAL CONSTRAINTS =====
        prompt_parts.append(self._safety_constraints())
        
        return "\n\n".join(prompt_parts)
    
    def _system_instructions(self, analysis: QuestionAnalysis, course_name: str) -> str:
        """Generate system instructions based on question analysis."""
        lines = [
            "SYSTEM INSTRUCTIONS:",
            f"You are a precise tutor for '{course_name}'.",
            f"Answer ONLY using evidence from the course materials below.",
            "",
            analysis.get_instruction_prompt(),
            "",
            f"Expected answer length: ~{analysis.expected_answer_length} characters",
        ]
        return "\n".join(lines)
    
    def _format_evidence_section(self, chunks: List[str], analysis: QuestionAnalysis) -> str:
        """Format evidence in a clear, scannable way."""
        lines = ["EVIDENCE FROM COURSE MATERIALS:"]
        lines.append(f"(Top {len(chunks)} relevant passages)")
        lines.append("")
        
        for i, chunk in enumerate(chunks[:5], 1):  # Limit to top 5
            # Truncate very long chunks
            display_chunk = chunk[:300] if len(chunk) > 300 else chunk
            if len(chunk) > 300:
                display_chunk += "..."
            
            lines.append(f"[{i}] {display_chunk}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_conversation_context(self, history: List[str]) -> str:
        """Format conversation history for follow-up questions."""
        lines = [
            "CONVERSATION CONTEXT:",
            "(This is a follow-up question. Remember the previous discussion.)",
            "",
        ]
        
        for i, msg in enumerate(history[-3:], 1):  # Last 3 messages
            lines.append(f"{i}. {msg[:150]}")
        
        return "\n".join(lines)
    
    def _answer_format_instructions(self, analysis: QuestionAnalysis) -> str:
        """Format instructions for how to answer."""
        lines = [
            "ANSWER FORMAT:",
            "1. Answer DIRECTLY and CIT using the evidence above.",
        ]
        
        if analysis.requires_examples:
            lines.append("2. Include relevant examples from the materials.")
        
        if analysis.requires_explanation:
            lines.append("2. Explain the concept clearly.")
        
        lines.extend([
            "3. If exact information isn't in materials, say: 'This specific point isn't covered in the course materials.'",
            "4. Keep answer focused and relevant to the question.",
            f"5. Target length: {analysis.expected_answer_length} characters.",
        ])
        
        return "\n".join(lines)
    
    @staticmethod
    def _safety_constraints() -> str:
        """Non-negotiable constraints to prevent hallucination."""
        return """CRITICAL CONSTRAINTS:
✓ ONLY use information from the evidence above
✓ Do NOT add outside knowledge
✓ Do NOT invent examples not in materials
✓ Do NOT guess or assume
✓ Be honest if materials don't answer the question
✓ Reference specific passages when possible
✓ Do NOT speculate about topics not in materials"""


class ResponseValidator:
    """Validate that responses are properly grounded and non-random."""
    
    @staticmethod
    def validate_answer(
        answer: str,
        question: str,
        evidence_chunks: List[str],
        analysis: QuestionAnalysis,
    ) -> tuple[bool, str, float]:
        """
        Validate that answer is properly grounded.
        Returns (is_valid, reason, confidence_score)
        """
        
        if not answer or len(answer) < 20:
            return False, "Answer is too short", 0.0
        
        # Check 1: Does answer address the question?
        relevance = ResponseValidator._check_question_relevance(answer, question, analysis)
        if relevance < 0.5:
            return False, "Answer doesn't address the question", relevance
        
        # Check 2: Does answer use evidence?
        evidence_usage = ResponseValidator._check_evidence_usage(answer, evidence_chunks)
        if evidence_usage < 0.3:
            return False, "Answer doesn't use provided evidence", evidence_usage
        
        # Check 3: Does answer avoid hallucination?
        hallucination_risk = ResponseValidator._check_hallucination_risk(answer)
        if hallucination_risk > 0.6:
            return False, "Answer contains likely hallucinations", 1.0 - hallucination_risk
        
        # Combine scores
        confidence_score = (relevance * 0.4 + evidence_usage * 0.4 + (1.0 - hallucination_risk) * 0.2)
        
        if confidence_score < 0.6:
            return False, "Overall answer quality is low", confidence_score
        
        return True, "Answer is well-grounded", confidence_score
    
    @staticmethod
    def _check_question_relevance(answer: str, question: str, analysis: QuestionAnalysis) -> float:
        """Check if answer actually addresses the question."""
        answer_lower = answer.lower()
        question_words = set(analysis.key_keywords)
        
        # Count how many key concepts appear in answer
        matches = sum(1 for kw in question_words if kw in answer_lower)
        
        return min(matches / max(len(question_words), 1), 1.0)
    
    @staticmethod
    def _check_evidence_usage(answer: str, evidence_chunks: List[str]) -> float:
        """Check if answer uses the provided evidence."""
        if not evidence_chunks:
            return 0.0
        
        # Check for exact phrase matches from evidence
        answer_lower = answer.lower()
        matches = 0
        
        for chunk in evidence_chunks:
            chunk_lower = chunk.lower()
            # Check for 3+ word sequences
            words = chunk_lower.split()
            for i in range(len(words) - 3):
                phrase = " ".join(words[i:i+3])
                if phrase in answer_lower:
                    matches += 1
                    break
        
        return min(matches / max(len(evidence_chunks), 1), 1.0)
    
    @staticmethod
    def _check_hallucination_risk(answer: str) -> float:
        """Detect signs of hallucination."""
        risk_factors = []
        
        # Generic/vague language (sign of bullshitting)
        generic_phrases = [
            'in general', 'typically', 'usually', 'often', 'might',
            'could be', 'sometimes', 'may', 'according to some',
        ]
        generic_count = sum(1 for phrase in generic_phrases if phrase in answer.lower())
        risk_factors.append(min(generic_count / max(len(answer.split()), 1), 0.3))
        
        # Made-up citations
        if re.search(r'\b(studies show|research suggests|evidence indicates|it is known that)\b', answer, re.IGNORECASE):
            risk_factors.append(0.2)
        
        # Overly confident claims without evidence
        confident_claims = re.findall(r'\b(definitely|certainly|undoubtedly|obviously)\b', answer, re.IGNORECASE)
        if confident_claims:
            risk_factors.append(min(len(confident_claims) / 5, 0.2))
        
        return sum(risk_factors) / max(len(risk_factors), 1)
