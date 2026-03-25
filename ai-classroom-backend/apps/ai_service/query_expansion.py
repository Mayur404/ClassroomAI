"""
Query expansion and semantic enhancement for better search results.
Expands queries with synonyms and related terms.
"""
import logging
from typing import Optional
import re

logger = logging.getLogger(__name__)

# Domain-specific synonym mappings for educational content
EDUCATIONAL_SYNONYMS = {
    "algorithm": ["algorithms", "procedure", "method", "approach"],
    "data structure": ["structure", "data type", "collection"],
    "function": ["method", "procedure", "routine", "subroutine"],
    "variable": ["parameter", "argument", "value", "property"],
    "loop": ["iteration", "loop", "repetition", "cycle"],
    "condition": ["if statement", "conditional", "decision", "check"],
    "class": ["type", "category", "definition", "object"],
    "inheritance": ["inherit", "extend", "derive", "subclass"],
    "polymorphism": ["override", "overload", "virtual", "interface"],
    "abstraction": ["abstract", "hiding", "encapsulation"],
    "api": ["interface", "endpoint", "service", "protocol"],
    "database": ["store", "repository", "cache", "table"],
    "network": ["connection", "communication", "socket", "protocol"],
    "security": ["encryption", "authentication", "protection", "permission"],
    "performance": ["speed", "efficiency", "optimization", "throughput"],
}

# Question type to search strategy
QUESTION_STRATEGIES = {
    "what_is": [
        "definition",
        "meaning",
        "explain",
        "concept",
        "introduction",
    ],
    "how_to": [
        "steps",
        "procedure",
        "algorithm",
        "implementation",
        "example",
    ],
    "why": [
        "reason",
        "purpose",
        "advantage",
        "benefit",
        "motivation",
    ],
    "when": [
        "condition",
        "scenario",
        "situation",
        "case",
        "context",
    ],
    "where": [
        "location",
        "section",
        "chapter",
        "topic",
        "chapter",
    ],
}

class QueryExpander:
    """Expand queries for better search coverage."""
    
    def __init__(self):
        self.synonyms = EDUCATIONAL_SYNONYMS
        self.strategies = QUESTION_STRATEGIES
    
    def expand_query(self, query: str, max_expansions: int = 3) -> list[str]:
        """Generate expanded versions of the query."""
        expansions = [query]  # Always include original
        
        # Find keywords that have synonyms
        query_lower = query.lower()
        for term, synonyms in self.synonyms.items():
            if term in query_lower:
                # Create variations with different synonyms
                for i, syn in enumerate(synonyms[:max_expansions]):
                    expansion = query_lower.replace(term, syn)
                    if expansion not in expansions:
                        expansions.append(expansion)
        
        # Detect question type and add strategy terms
        question_type = self._detect_question_type(query)
        if question_type in self.strategies:
            strategy_terms = self.strategies[question_type]
            # Create variations with strategy terms
            base_query = query.rstrip("?").strip()
            for term in strategy_terms[:2]:
                expansion = f"{base_query} {term}"
                if expansion not in expansions:
                    expansions.append(expansion)
        
        logger.debug(f"Query expansions: {expansions}")
        return expansions[:max_expansions + 1]  # Original + max_expansions
    
    def _detect_question_type(self, query: str) -> str:
        """Detect the type of question being asked."""
        query_lower = query.lower()
        
        if query_lower.startswith(("what is", "what are", "define")):
            return "what_is"
        elif query_lower.startswith(("how do", "how can", "how to", "how")):
            return "how_to"
        elif query_lower.startswith(("why", "reason")):
            return "why"
        elif query_lower.startswith(("when", "what time")):
            return "when"
        elif query_lower.startswith(("where", "section", "chapter")):
            return "where"
        
        return "general"


class SemanticMatcher:
    """Match queries semantically against document content."""
    
    @staticmethod
    def calculate_similarity(query_tokens: set[str], 
                            content_tokens: set[str]) -> float:
        """Calculate similarity between query and content (Jaccard similarity)."""
        if not query_tokens or not content_tokens:
            return 0.0
        
        intersection = len(query_tokens & content_tokens)
        union = len(query_tokens | content_tokens)
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def extract_tokens(text: str, remove_stopwords: bool = True) -> set[str]:
        """Extract meaningful tokens from text."""
        stopwords = {
            "a", "an", "and", "are", "as", "at", "be", "by", "for",
            "from", "in", "is", "it", "of", "on", "or", "that", "the",
            "to", "was", "were", "what", "where", "which", "who", "why",
            "how", "the", "this", "that", "these", "those", "i", "you",
            "he", "she", "it", "we", "they"
        }
        
        # Tokenize and clean
        tokens = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
        
        if remove_stopwords:
            tokens = [t for t in tokens if t not in stopwords]
        
        return set(tokens)


def expand_and_search(query: str, original_search_func, max_expansions: int = 3) -> list[str]:
    """Search with query expansion."""
    expander = QueryExpander()
    expansions = expander.expand_query(query, max_expansions=max_expansions)
    
    # Search with all expansions
    all_results = []
    seen = set()
    
    for expanded_query in expansions:
        results = original_search_func(expanded_query)
        for result in results:
            result_key = result.lower().strip()
            if result_key not in seen:
                seen.add(result_key)
                all_results.append(result)
    
    logger.info(f"Expanded search: {len(expansions)} queries -> {len(all_results)} unique results")
    return all_results
