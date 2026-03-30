"""
Database query optimization utilities and decorators.
Helps identify and fix N+1 query problems.
"""
import logging
from typing import List, Dict, Any
from django.db.models import Prefetch, QuerySet, Model
from functools import wraps
from django.core.cache import cache
import time

logger = logging.getLogger(__name__)


class QueryOptimizationHelper:
    """Helper class for optimizing Django ORM queries."""
    
    @staticmethod
    def auto_select_related(queryset: QuerySet, depth: int = 2) -> QuerySet:
        """
        Automatically apply select_related for foreign keys.
        
        Args:
            queryset: Base queryset
            depth: Depth of relations to follow
            
        Returns:
            Optimized queryset
        """
        model = queryset.model
        
        # Get all foreign key fields
        fk_fields = [
            f.name for f in model._meta.get_fields()
            if hasattr(f, 'many_to_one') and f.many_to_one
        ]
        
        # Apply select_related
        for field in fk_fields[:depth]:  # Limit depth to prevent over-fetching
            queryset = queryset.select_related(field)
        
        return queryset
    
    @staticmethod
    def auto_prefetch_related(queryset: QuerySet, depth: int = 1) -> QuerySet:
        """
        Automatically apply prefetch_related for reverse relations.
        
        Args:
            queryset: Base queryset
            depth: Depth of relations to follow
            
        Returns:
            Optimized queryset
        """
        model = queryset.model
        
        # Get all reverse relation fields
        reverse_relations = [
            f.name for f in model._meta.get_fields()
            if hasattr(f, 'one_to_many') or hasattr(f, 'many_to_many')
        ]
        
        # Apply prefetch_related selectively (avoid over-fetching)
        for field in reverse_relations[:depth]:
            queryset = queryset.prefetch_related(field)
        
        return queryset
    
    @staticmethod
    def analyze_queryset(queryset: QuerySet) -> Dict[str, Any]:
        """
        Analyze queryset for potential optimization issues.
        
        Returns:
            Analysis report
        """
        return {
            "query": str(queryset.query),
            "count": queryset.count(),
            "selected_related": queryset.query.select_related or {},
            "prefetching_related": queryset._prefetch_related_lookups or [],
        }


def optimize_queries(func):
    """
    Decorator to optimize queries in view methods.
    Wraps function and applies auto-optimization.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get request for timing
        request = args[0].request if hasattr(args[0], 'request') else None
        
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        if execution_time > 1.0:  # Log slow queries
            logger.warning(
                f"Slow query in {func.__name__}: {execution_time:.2f}s",
                extra={
                    "function": func.__name__,
                    "execution_time_ms": execution_time * 1000,
                }
            )
        
        return result
    
    return wrapper


# ============================================================================
# QUERYSET OPTIMIZATION PATTERNS
# ============================================================================

class CourseOptimizationMixin:
    """Mixin for optimized course queries."""
    
    def get_course_with_relations(self, course_id: int) -> Model:
        """Get course with all related data pre-fetched."""
        from apps.courses.models import Course
        
        return (
            Course.objects
            .select_related("instructor")
            .prefetch_related("materials", "assignments", "students")
            .get(id=course_id)
        )
    
    def get_course_list_optimized(self) -> QuerySet:
        """Get all courses with optimized queries."""
        from apps.courses.models import Course
        
        return (
            Course.objects
            .select_related("instructor")
            .prefetch_related("materials")
            .only(
                "id", "title", "description", "created_at",
                "instructor__id", "instructor__name"
            )
        )


class AssignmentOptimizationMixin:
    """Mixin for optimized assignment queries."""
    
    def get_assignment_with_submissions(self, assignment_id: int) -> Model:
        """Get assignment with submissions."""
        from apps.assignments.models import Assignment
        from apps.submissions.models import Submission
        
        submissions = Submission.objects.select_related("student")
        
        return (
            Assignment.objects
            .select_related("course")
            .prefetch_related(
                Prefetch("submission_set", queryset=submissions)
            )
            .get(id=assignment_id)
        )
    
    def get_assignments_by_course(self, course_id: int) -> QuerySet:
        """Get all assignments for a course."""
        from apps.assignments.models import Assignment
        
        return (
            Assignment.objects
            .filter(course_id=course_id)
            .select_related("course")
            .only("id", "title", "description", "created_at")
            .order_by("-created_at")
        )


class ChatOptimizationMixin:
    """Mixin for optimized chat queries."""
    
    def get_conversation_optimized(self, conversation_id: int) -> QuerySet:
        """Get chat messages with optimizations."""
        from apps.chat.models import ChatMessage
        
        return (
            ChatMessage.objects
            .filter(conversation_id=conversation_id)
            .select_related("user", "conversation")
            .only(
                "id", "message", "response", "created_at",
                "user__id", "user__email",
                "conversation__id", "conversation__course_id"
            )
            .order_by("created_at")
        )


# ============================================================================
# BATCH OPERATION OPTIMIZATIONS
# ============================================================================

class BatchOperationOptimizer:
    """Optimize batch operations."""
    
    @staticmethod
    def bulk_create_with_defaults(model: Model, objects: List[Dict], batch_size: int = 1000):
        """
        Efficiently create multiple objects.
        
        Args:
            model: Django model class
            objects: List of object dictionaries
            batch_size: Batch size for creation
        """
        instances = [model(**obj) for obj in objects]
        
        # Create in batches
        created = []
        for i in range(0, len(instances), batch_size):
            batch = instances[i:i+batch_size]
            created.extend(model.objects.bulk_create(batch))
        
        logger.info(f"Bulk created {len(created)} {model.__name__} objects")
        return created
    
    @staticmethod
    def bulk_update_optimized(model: Model, updates: Dict[int, Dict], batch_size: int = 1000):
        """
        Efficiently update multiple objects.
        
        Args:
            model: Django model class
            updates: Dict of {object_id: {field: value}}
            batch_size: Batch size for updates
        """
        instances = []
        
        for obj_id, fields in updates.items():
            obj = model(id=obj_id, **fields)
            instances.append(obj)
        
        # Update in batches (requires all objects to have same fields)
        fields_to_update = list(next(iter(updates.values())).keys()) if updates else []
        
        updated = 0
        for i in range(0, len(instances), batch_size):
            batch = instances[i:i+batch_size]
            updated += len(
                model.objects.bulk_update(
                    batch,
                    fields_to_update,
                    batch_size=batch_size
                )
            )
        
        logger.info(f"Bulk updated {updated} {model.__name__} objects")
        return updated


# ============================================================================
# INDEX AND QUERY ANALYSIS
# ============================================================================

class QueryAnalyzer:
    """Analyze and report on query performance."""
    
    @staticmethod
    def get_slow_queryset(queryset: QuerySet, threshold_ms: int = 1000) -> Dict[str, Any]:
        """Identify if queryset is slow."""
        from django.test.utils import override_settings
        from django.db import connection, reset_queries
        
        with override_settings(DEBUG=True):
            reset_queries()
            
            # Execute queryset
            list(queryset)
            
            slow_queries = [
                q for q in connection.queries
                if float(q['time']) > threshold_ms / 1000
            ]
            
            return {
                "total_queries": len(connection.queries),
                "slow_queries": len(slow_queries),
                "total_time": sum(float(q['time']) for q in connection.queries),
                "queries": slow_queries,
            }
    
    @staticmethod
    def recommend_indexes(model: Model) -> List[str]:
        """Recommend indexes for a model based on common queries."""
        recommendations = []
        
        # Get all foreign key fields - should be indexed
        for field in model._meta.get_fields():
            if hasattr(field, 'many_to_one') and field.many_to_one:
                recommendations.append(f"Add index on {model.__name__}.{field.name}")
        
        return recommendations
