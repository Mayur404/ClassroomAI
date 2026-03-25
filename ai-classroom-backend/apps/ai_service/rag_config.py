"""
RAG Configuration and Performance Tuning
Fine-tune RAG behavior for your use case
"""

# ============================================================================
# SEARCH CONFIGURATION
# ============================================================================

# Number of chunks to retrieve for context
DEFAULT_TOP_K = 6

# For heading queries, how many sections to consider
HEADING_SEARCH_TOP_K = 10

# Number of evidence snippets to extract from chunks
EVIDENCE_LIMIT = 3

# ============================================================================
# CACHING CONFIGURATION  
# ============================================================================

# How long to cache parser results (seconds)
PARSER_CACHE_TIMEOUT = 3600 * 24  # 24 hours

# How long to cache section matches (seconds)
SECTION_MATCH_CACHE_TIMEOUT = 3600  # 1 hour

# How long to cache ranked results (seconds)
RELEVANCE_CACHE_TIMEOUT = 1800  # 30 minutes

# How long to cache search results (seconds)
SEARCH_CACHE_TIMEOUT = 3600  # 1 hour

# ============================================================================
# ANSWER GENERATION CONFIGURATION
# ============================================================================

# Temperature for LLM (lower = more deterministic)
OLLAMA_TEMPERATURE = 0.05

# Max tokens to generate
OLLAMA_CHAT_NUM_PREDICT = 320

# Context window size
OLLAMA_NUM_CTX = 4096

# Keep model in memory for this long
OLLAMA_KEEP_ALIVE = "30m"

# ============================================================================
# DOCUMENT STRUCTURE PARSING CONFIGURATION
# ============================================================================

# Max sections to extract
MAX_SECTIONS_PER_DOCUMENT = 50

# Min section heading length
MIN_SECTION_HEADING_LENGTH = 4

# Max section heading length
MAX_SECTION_HEADING_LENGTH = 100

# Keywords per section to index
KEYWORDS_PER_SECTION = 5

# ============================================================================
# QUESTION CLASSIFICATION CONFIGURATION
# ============================================================================

# Estimated answer lengths for different question types
ANSWER_LENGTH_ESTIMATION = {
    "factual": 250,  # "What is X?"
    "conceptual": 350,  # "Why does X happen?"
    "procedural": 400,  # "How to do X?"
    "list": 450,  # "List all X"
    "comparison": 400,  # "Compare X and Y"
    "general": 300,  # Default
}

# ============================================================================
# RELEVANCE SCORING CONFIGURATION
# ============================================================================

# Scoring weights for relevance ranking
RELEVANCE_WEIGHTS = {
    "exact_phrase_match": 2.0,  # Query appears verbatim
    "keyword_match": 0.5,  # Per matching keyword
    "section_heading_format": 0.3,  # Looks like a heading
    "length_appropriateness": 0.2,  # 50-400 word range
}

# Min score to consider a result relevant
MIN_RELEVANCE_SCORE = 0.3

# ============================================================================
# INDEXING CONFIGURATION
# ============================================================================

# Chunk size for document chunking
DEFAULT_CHUNK_SIZE = 500

# Overlap between chunks (words)
DEFAULT_CHUNK_OVERLAP = 100

# Adaptive chunking: increase chunk size for longer documents
ADAPTIVE_CHUNKING = True

# ============================================================================
# HYBRID SEARCH CONFIGURATION  
# ============================================================================

# Weight for vector search results (0-1)
VECTOR_SEARCH_WEIGHT = 0.7

# Weight for lexical search results (0-1)
LEXICAL_SEARCH_WEIGHT = 0.3

# Cache limit for lexical chunks
LEXICAL_CHUNK_CACHE_LIMIT = 96

# Cache limit for search results
SEARCH_RESULT_CACHE_LIMIT = 192

# ============================================================================
# PERFORMANCE TUNING
# ============================================================================

# Enable caching (disable for testing)
ENABLE_CACHING = True

# Enable query expansion
ENABLE_QUERY_EXPANSION = True

# Enable section matching
ENABLE_SECTION_MATCHING = True

# Connection pooling for Ollama
OLLAMA_POOL_CONNECTIONS = 20
OLLAMA_POOL_MAXSIZE = 20

# ============================================================================
# TUNING RECOMMENDATIONS
# ============================================================================

"""
For SPEED (low latency):
- Reduce DEFAULT_TOP_K to 3-4
- Reduce EVIDENCE_LIMIT to 2
- Increase cache TTLs
- Enable ENABLE_CACHING = True

For ACCURACY (better answers):
- Increase DEFAULT_TOP_K to 8-10
- Increase EVIDENCE_LIMIT to 4-5
- Decrease OLLAMA_TEMPERATURE to 0.02
- Enable ENABLE_QUERY_EXPANSION = True

For MEMORY (small deployments):
- Reduce cache timeouts
- Reduce LEXICAL_CHUNK_CACHE_LIMIT
- Set ADAPTIVE_CHUNKING = True
- Use smaller OLLAMA_NUM_CTX

For SCALABILITY (many users):
- Increase OLLAMA_POOL_CONNECTIONS
- Increase OLLAMA_POOL_MAXSIZE
- Use Redis for distributed caching
- Enable batch processing
"""

# ============================================================================
# FEATURE FLAGS
# ============================================================================

FEATURES = {
    "heading_queries": True,  # Detect and handle heading queries
    "document_structure": True,  # Extract and use document structure
    "intelligent_ranking": True,  # Re-rank results by relevance
    "answer_formatting": True,  # Format answers with proper sources
    "question_classification": True,  # Classify question types
    "batch_search": True,  # Enable batch search operations
}
