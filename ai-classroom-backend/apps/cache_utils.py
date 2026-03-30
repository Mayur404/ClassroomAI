"""
Advanced caching utilities with cache invalidation and warming.
Provides smart caching for RAG searches, answers, and frequently accessed data.
"""
import hashlib
import json
import logging
from typing import Any, Callable, Optional, List, Dict
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from functools import wraps
import time

logger = logging.getLogger(__name__)


# ============================================================================
# CACHE KEY GENERATION
# ============================================================================

class CacheKeyBuilder:
    """Utility for generating consistent cache keys."""
    
    PREFIX = "aiclass"
    SEPARATORS = ":"
    
    @staticmethod
    def build(*components: Any, version: int = 1) -> str:
        """
        Build a cache key from components.
        
        Args:
            components: Key components (strings or integers)
            version: Version number for cache key format
            
        Returns:
            Formatted cache key
        """
        key_parts = [CacheKeyBuilder.PREFIX, f"v{version}"]
        
        for component in components:
            if component is not None:
                # Convert to string and escape special chars
                part = str(component).replace(CacheKeyBuilder.SEPARATORS, "_")
                key_parts.append(part)
        
        return CacheKeyBuilder.SEPARATORS.join(key_parts)
    
    @staticmethod
    def hash_content(*content: str) -> str:
        """Generate hash from content for cache key."""
        combined = "".join(str(c) for c in content)
        return hashlib.md5(combined.encode()).hexdigest()
    
    # Predefined key builders for common patterns
    @staticmethod
    def search_cache(course_id: int, query: str) -> str:
        """Cache key for search results."""
        query_hash = CacheKeyBuilder.hash_content(query)
        return CacheKeyBuilder.build("search", course_id, query_hash)
    
    @staticmethod
    def answer_cache(chat_id: int, message_id: int) -> str:
        """Cache key for generated answers."""
        return CacheKeyBuilder.build("answer", chat_id, message_id)
    
    @staticmethod
    def rag_cache(course_id: int, query: str) -> str:
        """Cache key for RAG retrieval."""
        query_hash = CacheKeyBuilder.hash_content(query)
        return CacheKeyBuilder.build("rag", course_id, query_hash)
    
    @staticmethod
    def course_summary_cache(course_id: int) -> str:
        """Cache key for course summary."""
        return CacheKeyBuilder.build("course_summary", course_id)
    
    @staticmethod
    def course_materials_cache(course_id: int) -> str:
        """Cache key for course materials list."""
        return CacheKeyBuilder.build("course_materials", course_id)
    
    @staticmethod
    def assignment_list_cache(course_id: int) -> str:
        """Cache key for assignment list."""
        return CacheKeyBuilder.build("assignments", course_id)


# ============================================================================
# CACHE INVALIDATION
# ============================================================================

class CacheInvalidator:
    """Manages cache invalidation across related objects."""
    
    # Mapping of models to cache key patterns they invalidate
    INVALIDATION_MAP = {
        "CourseMaterial": [
            "course_materials:*",
            "search:*",
            "rag:*",
            "course_summary:*",
        ],
        "Course": [
            "course_summary:*",
            "course_materials:*",
            "assignments:*",
        ],
        "Assignment": [
            "assignments:*",
        ],
        "ChatMessage": [
            "answer:*",
        ],
    }
    
    @staticmethod
    def invalidate_pattern(pattern: str) -> int:
        """
        Invalidate all cache keys matching pattern.
        
        Args:
            pattern: Cache key pattern (supports * wildcard)
            
        Returns:
            Number of keys invalidated
        """
        try:
            # For Redis, we can use pattern matching
            if pattern.endswith("*"):
                base_pattern = pattern.replace("*", "")
                # This requires Redis cache backend with pattern support
                keys = cache.delete_many([k for k in cache.keys(f"{base_pattern}*")])
                logger.info(f"Invalidated {len(keys) if keys else 0} cache keys matching {pattern}")
                return len(keys) if keys else 0
            else:
                cache.delete(pattern)
                logger.info(f"Invalidated cache key: {pattern}")
                return 1
        except Exception as e:
            logger.warning(f"Failed to invalidate cache pattern {pattern}: {str(e)}")
            return 0
    
    @staticmethod
    def invalidate_by_model(model_name: str) -> int:
        """
        Invalidate cache patterns related to a model.
        
        Args:
            model_name: Django model name
            
        Returns:
            Total keys invalidated
        """
        patterns = CacheInvalidator.INVALIDATION_MAP.get(model_name, [])
        total_invalidated = 0
        
        for pattern in patterns:
            total_invalidated += CacheInvalidator.invalidate_pattern(pattern)
        
        return total_invalidated


# ============================================================================
# CACHE DECORATORS
# ============================================================================

def cached_method(timeout: int = 300, key_builder: Optional[Callable] = None):
    """
    Decorator for caching method results.
    
    Args:
        timeout: Cache timeout in seconds
        key_builder: Optional callable to generate cache key
        
    Example:
        @cached_method(timeout=3600)
        def get_course_data(self, course_id):
            return expensive_query(course_id)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default: use function name and all arguments
                key_parts = [func.__name__] + list(args) + list(kwargs.values())
                cache_key = CacheKeyBuilder.build(*key_parts)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return result
            
            # Cache miss: execute function
            logger.debug(f"Cache miss for {cache_key}, executing {func.__name__}")
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, timeout)
            
            return result
        
        return wrapper
    
    return decorator


def cached_queryset(timeout: int = 300, key_builder: Optional[Callable] = None):
    """
    Decorator for caching queryset results.
    Automatically converts querysets to lists for caching.
    
    Args:
        timeout: Cache timeout in seconds
        key_builder: Optional callable to generate cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                key_parts = [func.__name__] + list(args) + list(kwargs.values())
                cache_key = CacheKeyBuilder.build(*key_parts)
            
            # Try to get from cache
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for queryset {cache_key}")
                return cached_data
            
            # Cache miss: execute function
            result = func(*args, **kwargs)
            
            # Convert queryset to list if necessary
            if hasattr(result, "model"):
                result = list(result)
            
            # Store in cache
            cache.set(cache_key, result, timeout)
            
            return result
        
        return wrapper
    
    return decorator


# ============================================================================
# CACHE WARMING
# ============================================================================

class CacheWarmer:
    """Pre-loads frequently accessed data into cache."""
    
    @staticmethod
    def warm_course_data(course_id: int, timeout: int = 3600) -> int:
        """
        Pre-load course data into cache.
        
        Args:
            course_id: Course ID
            timeout: Cache timeout
            
        Returns:
            Number of items cached
        """
        try:
            from apps.courses.models import Course, CourseMaterial
            
            # Load course summary
            course = Course.objects.select_related("instructor").get(id=course_id)
            cache_key = CacheKeyBuilder.course_summary_cache(course_id)
            cache.set(cache_key, {
                "title": course.title,
                "description": course.description,
                "instructor": str(course.instructor),
            }, timeout)
            
            # Load course materials
            materials = list(CourseMaterial.objects.filter(course_id=course_id).values())
            cache_key = CacheKeyBuilder.course_materials_cache(course_id)
            cache.set(cache_key, materials, timeout)
            
            logger.info(f"Warmed cache for course {course_id}")
            return 2
        except Exception as e:
            logger.error(f"Failed to warm course cache: {str(e)}")
            return 0
    
    @staticmethod
    def warm_popular_searches(course_id: int, limit: int = 10) -> int:
        """
        Pre-load frequently searched queries.
        (Requires analytics data)
        
        Args:
            course_id: Course ID
            limit: Number of popular searches
            
        Returns:
            Number of searches warmed
        """
        # This would require tracking popular searches
        # For now, just return 0
        return 0


# ============================================================================
# SIGNAL HANDLERS FOR AUTOMATIC CACHE INVALIDATION
# ============================================================================

def setup_cache_invalidation():
    """
    Register signal handlers for automatic cache invalidation.
    Call this in app's ready() method.
    """
    from django.apps import apps
    
    # This would be called from apps/__init__.py or apps/*/apps.py
    # Example:
    # from apps.cache_utils import setup_cache_invalidation
    # setup_cache_invalidation()
    
    pass


# ============================================================================
# CACHE STATISTICS
# ============================================================================

class CacheStats:
    """Track cache performance metrics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0
    
    def report(self) -> Dict[str, Any]:
        """Generate cache performance report."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "hit_rate": f"{self.hit_rate:.1f}%",
            "total_operations": self.hits + self.misses,
        }


# Global cache stats instance
_cache_stats = CacheStats()


def get_cache_stats() -> Dict[str, Any]:
    """Get current cache statistics."""
    return _cache_stats.report()
