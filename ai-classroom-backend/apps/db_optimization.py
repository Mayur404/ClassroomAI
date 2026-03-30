"""
Database optimization utilities: strategic indexes, batch operations, query analysis
"""
from django.db import models, connection
from django.db.models import Q, F, Prefetch, Count, Max, Min, Avg
from django.db.models.signals import post_migrate
from django.dispatch import receiver
import logging
import time
from typing import List, Dict, Any, QuerySet
from contextlib import contextmanager

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE INDEXES
# ============================================================================

class DatabaseIndexManager:
    """
    Manages creation of strategic indexes for performance.
    
    Indexes to create:
    - Course: (instructor, created_at) - for filtering instructor's courses
    - Material: (course, indexed_at, created_at) - for retrieval optimization
    - Chat: (course, user, created_at) - for conversation history
    - Submission: (assignment, user, created_at) - for grade lookups
    - Answer: (query_hash, user) - for caching
    """
    
    @staticmethod
    def get_indexes() -> List[Dict[str, Any]]:
        """Return list of recommended indexes."""
        return [
            {
                "app": "courses",
                "model": "Course",
                "fields": ["instructor", "-created_at"],
                "name": "idx_course_instructor_date",
            },
            {
                "app": "courses",
                "model": "CourseMaterial",
                "fields": ["course", "indexed_at", "-created_at"],
                "name": "idx_material_course_status_date",
            },
            {
                "app": "courses",
                "model": "CourseMaterial",
                "fields": ["extraction_quality_score"],
                "name": "idx_material_quality",
            },
            {
                "app": "chat",
                "model": "ChatMessage",
                "fields": ["course", "user", "-created_at"],
                "name": "idx_chat_course_user_date",
            },
            {
                "app": "submissions",
                "model": "Submission",
                "fields": ["assignment", "user", "-created_at"],
                "name": "idx_submission_assignment_user",
            },
            {
                "app": "submissions",
                "model": "Submission",
                "fields": ["graded", "-created_at"],
                "name": "idx_submission_graded",
            },
            {
                "app": "ai_service",
                "model": "QueryCache",
                "fields": ["query_hash", "user", "-created_at"],
                "name": "idx_cache_query_user_date",
            },
        ]
    
    @staticmethod
    def create_index_sql(table: str, fields: List[str], name: str) -> str:
        """Generate SQL for creating index."""
        # Handle descending order
        clean_fields = []
        for field in fields:
            if field.startswith("-"):
                clean_fields.append(f"{field[1:]} DESC")
            else:
                clean_fields.append(field)
        
        field_list = ", ".join(clean_fields)
        return f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({field_list});"
    
    @staticmethod
    def run_migrations():
        """Execute index creation after migrations."""
        logger.info("Running database optimization migrations")
        indexes = DatabaseIndexManager.get_indexes()
        
        with connection.cursor() as cursor:
            for index in indexes:
                try:
                    # Convert Django app/model to table name
                    app = index["app"]
                    model = index["model"]
                    table = f"{app}_{model.lower()}"
                    
                    sql = DatabaseIndexManager.create_index_sql(
                        table, index["fields"], index["name"]
                    )
                    cursor.execute(sql)
                    logger.info(f"Created index: {index['name']}")
                except Exception as e:
                    logger.warning(f"Failed to create index {index['name']}: {e}")


# Register index creation after migrations
@receiver(post_migrate)
def create_db_indexes(sender, **kwargs):
    """Auto-run index creation after migrations."""
    if kwargs.get('apps'):
        # Only run for ai_service app
        if sender.__name__ == 'apps.ai_service.apps':
            DatabaseIndexManager.run_migrations()


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

class BatchOperationManager:
    """
    Optimizes bulk operations: insert, update, delete
    Reduces N+1 queries, batches operations for efficiency
    """
    
    @staticmethod
    def bulk_create_with_progress(model_class, 
                                   objects: List,
                                   batch_size: int = 1000) -> int:
        """
        Create objects in batches with progress logging.
        
        Example:
            materials = [CourseMaterial(...) for _ in range(10000)]
            count = BatchOperationManager.bulk_create_with_progress(
                CourseMaterial, materials, batch_size=1000
            )
        """
        total = len(objects)
        created = 0
        
        for i in range(0, total, batch_size):
            batch = objects[i:i+batch_size]
            model_class.objects.bulk_create(batch, batch_size=batch_size)
            created += len(batch)
            
            progress = (created / total) * 100
            logger.info(f"Bulk create progress: {created}/{total} ({progress:.1f}%)")
        
        return created
    
    @staticmethod
    def bulk_update_with_progress(objects: List,
                                   fields: List[str],
                                   batch_size: int = 1000) -> int:
        """
        Update objects in batches.
        
        Example:
            submissions = Submission.objects.filter(graded=False)[:100]
            for sub in submissions:
                sub.graded = True
                sub.score = 95
            
            BatchOperationManager.bulk_update_with_progress(
                submissions, 
                fields=['graded', 'score'],
                batch_size=500
            )
        """
        from django.db.models import Model
        
        model_class = objects[0].__class__
        total = len(objects)
        updated = 0
        
        for i in range(0, total, batch_size):
            batch = objects[i:i+batch_size]
            model_class.objects.bulk_update(batch, fields, batch_size=batch_size)
            updated += len(batch)
            
            progress = (updated / total) * 100
            logger.info(f"Bulk update progress: {updated}/{total} ({progress:.1f}%)")
        
        return updated
    
    @staticmethod
    def bulk_delete_with_progress(queryset: QuerySet,
                                   batch_size: int = 1000) -> int:
        """
        Delete in batches with progress logging.
        """
        # Count before deleting
        total = queryset.count()
        deleted = 0
        
        while queryset.exists():
            # Delete in batches by ID
            ids = list(queryset.values_list('id', flat=True)[:batch_size])
            batch_qs = queryset.model.objects.filter(id__in=ids)
            count, _ = batch_qs.delete()
            deleted += count
            
            progress = (deleted / total) * 100
            logger.info(f"Bulk delete progress: {deleted}/{total} ({progress:.1f}%)")
        
        return deleted


# ============================================================================
# QUERY OPTIMIZATION UTILITIES
# ============================================================================

class QueryOptimizer:
    """
    Identifies and fixes N+1 queries, missing indexes, slow queries
    """
    
    @staticmethod
    @contextmanager
    def analyze_queries(label: str = "Query Analysis"):
        """
        Context manager to capture and analyze all database queries.
        
        Usage:
            with QueryOptimizer.analyze_queries("Chat retrieval"):
                messages = ChatMessage.objects.filter(course=course)
                for msg in messages:
                    print(msg.user.name)  # N+1 query here
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        
        with CaptureQueriesContext(connection) as context:
            yield context
        
        queries = context.captured_queries
        logger.info(f"\n=== {label} ===")
        logger.info(f"Total queries: {len(queries)}")
        
        # Group queries by type
        select_queries = [q for q in queries if q['sql'].strip().upper().startswith('SELECT')]
        insert_queries = [q for q in queries if q['sql'].strip().upper().startswith('INSERT')]
        update_queries = [q for q in queries if q['sql'].strip().upper().startswith('UPDATE')]
        delete_queries = [q for q in queries if q['sql'].strip().upper().startswith('DELETE')]
        
        logger.info(f"SELECT: {len(select_queries)}, INSERT: {len(insert_queries)}, "
                   f"UPDATE: {len(update_queries)}, DELETE: {len(delete_queries)}")
        
        # Find slow queries
        slow_queries = [q for q in queries if float(q.get('time', 0)) > 0.1]
        if slow_queries:
            logger.warning(f"Found {len(slow_queries)} slow queries (>100ms)")
            for q in slow_queries[:3]:  # Log top 3
                logger.warning(f"  {q['time']}s: {q['sql'][:100]}...")
        
        return {
            "total": len(queries),
            "select": len(select_queries),
            "insert": len(insert_queries),
            "update": len(update_queries),
            "delete": len(delete_queries),
            "slow": len(slow_queries),
        }
    
    @staticmethod
    def prefetch_related_objects(queryset: QuerySet, *relations) -> QuerySet:
        """
        Apply prefetch_related to prevent N+1 queries.
        
        Usage:
            messages = ChatMessage.objects.filter(course=course)
            messages = QueryOptimizer.prefetch_related_objects(
                messages,
                'user',
                'course__instructor'
            )
        """
        return queryset.prefetch_related(*relations)
    
    @staticmethod
    def select_related_objects(queryset: QuerySet, *relations) -> QuerySet:
        """
        Apply select_related for foreign key relationships.
        """
        return queryset.select_related(*relations)
    
    @staticmethod
    def generate_query_report() -> Dict[str, Any]:
        """
        Generate report of all slow queries and N+1 patterns.
        Run in development to identify optimization opportunities.
        """
        from django.test.utils import CaptureQueriesContext
        
        # This would require running test suite or app operations
        # and capturing all queries for analysis
        logger.warning("Query report generation requires full app operation")
        return {"status": "pending"}


# ============================================================================
# PERFORMANCE MONITORING
# ============================================================================

class PerformanceMonitor:
    """
    Monitors and logs database performance metrics.
    """
    
    @staticmethod
    def measure_query(query_func, *args, **kwargs) -> Dict[str, Any]:
        """
        Measure execution time of a database operation.
        
        Usage:
            result, metrics = PerformanceMonitor.measure_query(
                Course.objects.filter,
                instructor=user
            )
        """
        start = time.time()
        
        try:
            result = query_func(*args, **kwargs)
            
            # Force evaluation if QuerySet
            if hasattr(result, 'count'):
                count = result.count()
            else:
                count = len(result) if isinstance(result, list) else 1
            
            duration = (time.time() - start) * 1000
            
            return {
                "duration_ms": duration,
                "count": count,
                "status": "success",
            }
        except Exception as e:
            duration = (time.time() - start) * 1000
            return {
                "duration_ms": duration,
                "status": "error",
                "error": str(e),
            }
    
    @staticmethod
    def get_connection_stats() -> Dict[str, Any]:
        """Get database connection statistics."""
        from django.db import connection, connections
        
        stats = {
            "open_connections": len(connections),
            "queries_executed": len(connection.queries) if connection.queries else 0,
        }
        
        # Try to get pool stats if using connection pool
        try:
            pool_stats = connection.get_connection_pool_stats()
            stats["pool"] = pool_stats
        except:
            pass
        
        return stats


# ============================================================================
# N+1 QUERY FIXER DECORATOR
# ============================================================================

def optimize_queries(*relations):
    """
    Decorator to automatically apply prefetch/select_related.
    
    Usage:
        @optimize_queries('user', 'course__materials')
        def get_chat_messages(course_id):
            return ChatMessage.objects.filter(course_id=course_id)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            queryset = func(*args, **kwargs)
            
            if hasattr(queryset, 'prefetch_related'):
                queryset = queryset.prefetch_related(*relations)
            
            return queryset
        
        return wrapper
    
    return decorator


# ============================================================================
# EXAMPLE MODEL WITH OPTIMIZATIONS
# ============================================================================

"""
Example optimized model definition:

class ChatMessage(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['course', 'user', '-created_at']),
            models.Index(fields=['course', '-created_at']),
        ]
        ordering = ['-created_at']
    
    @optimize_queries('user', 'course')
    def get_with_related(self):
        return ChatMessage.objects.filter(id=self.id)
"""
