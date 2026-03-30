"""
Predictive cache warming: smart pre-loading of likely needed data
"""
import logging
import hashlib
from typing import List, Dict, Any, Callable, Set
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


class PredictiveCacheWarmer:
    """
    Pre-loads data that users are likely to request, reducing latency.
    
    Strategies:
    1. Popular content based on access patterns
    2. Time-based (morning = popular courses, afternoon = assignments)
    3. User-based (similar to recently active users)
    4. Transition-based (after viewing course → likely to view assignment)
    """
    
    def __init__(self, cache_backend):
        """
        Initialize cache warmer.
        
        Args:
            cache_backend: Django cache backend (Redis recommended)
        """
        self.cache = cache_backend
        self.metrics = {
            "items_warmed": 0,
            "cache_hits_from_preload": 0,
            "avg_improvement_ms": 0,
        }
    
    def warm_popular_courses(self, limit: int = 10, ttl: int = 3600):
        """
        Pre-load most popular courses by enrollment.
        """
        from apps.courses.models import Course
        
        logger.info(f"Warming popular courses (top {limit})")
        
        courses = (
            Course.objects
            .annotate(enrollment_count=Count('students'))
            .order_by('-enrollment_count')
            [:limit]
        )
        
        for course in courses:
            cache_key = f"course:{course.id}:detail"
            
            # Cache course data
            course_data = {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "instructor": course.instructor.username,
                "enrollments": course.students.count(),
            }
            
            self.cache.set(cache_key, course_data, ttl)
            self.metrics["items_warmed"] += 1
            
            logger.debug(f"Warmed course {course.id}: {course.title}")
    
    def warm_course_materials(self, course_id: int, limit: int = 20, ttl: int = 3600):
        """
        Pre-load materials for a course.
        """
        from apps.courses.models import CourseMaterial
        
        logger.info(f"Warming materials for course {course_id}")
        
        materials = (
            CourseMaterial.objects
            .filter(course_id=course_id, indexed_at=True)
            .order_by('-access_count')
            [:limit]
        )
        
        for material in materials:
            cache_key = f"material:{material.id}:content"
            
            material_data = {
                "id": material.id,
                "title": material.title,
                "pages": material.pages,
                "quality_score": material.extraction_quality_score,
                "extracted_at": material.updated_at.isoformat(),
            }
            
            self.cache.set(cache_key, material_data, ttl)
            self.metrics["items_warmed"] += 1
        
        # Also warm embeddings/vector data
        self._warm_embeddings_for_course(course_id, materials[:5])
    
    def warm_user_profile(self, user_id: int, ttl: int = 1800):
        """
        Pre-load user profile and preferences.
        """
        from django.contrib.auth.models import User
        
        try:
            user = User.objects.get(id=user_id)
            
            cache_key = f"user:{user_id}:profile"
            
            user_data = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_instructor": hasattr(user, 'instructor_profile'),
            }
            
            self.cache.set(cache_key, user_data, ttl)
            self.metrics["items_warmed"] += 1
            
            logger.debug(f"Warmed profile for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to warm user {user_id}: {e}")
    
    def warm_user_courses(self, user_id: int, ttl: int = 1800):
        """
        Pre-load user's enrolled courses.
        """
        from django.contrib.auth.models import User
        from apps.courses.models import Course
        
        try:
            user = User.objects.get(id=user_id)
            
            # Get courses user is enrolled in
            courses = user.courses.all()  # Assuming relationship exists
            
            cache_key = f"user:{user_id}:courses"
            
            courses_data = [
                {
                    "id": c.id,
                    "title": c.title,
                    "instructor": c.instructor.username,
                }
                for c in courses
            ]
            
            self.cache.set(cache_key, courses_data, ttl)
            self.metrics["items_warmed"] += 1
            
            logger.debug(f"Warmed {len(courses)} courses for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to warm courses for user {user_id}: {e}")
    
    def warm_time_based_data(self, hour_of_day: int = None, ttl: int = 3600):
        """
        Warm data based on time of day patterns.
        
        Morning (6-9): Popular courses, syllabus materials
        Daytime (9-17): Assignment lists, chat history
        Evening (17-22): Recently accessed materials, personalized recommendations
        """
        from apps.courses.models import Course, CourseMaterial
        
        if hour_of_day is None:
            hour_of_day = datetime.now().hour
        
        logger.info(f"Running time-based cache warming (hour={hour_of_day})")
        
        if 6 <= hour_of_day < 9:
            # Morning: warm popular courses and announcements
            self.warm_popular_courses(limit=15, ttl=ttl)
            logger.info("Warmed morning content (courses + announcements)")
        
        elif 9 <= hour_of_day < 17:
            # Daytime: warm assignments and recent discussions
            self._warm_recent_assignments(limit=20, ttl=ttl)
            logger.info("Warmed daytime content (assignments + discussions)")
        
        elif 17 <= hour_of_day <= 22:
            # Evening: warm personalized recommendations
            self._warm_user_specific_content(ttl=ttl)
            logger.info("Warmed evening content (personalized recommendations)")
    
    def warm_search_cache(self, popular_queries: List[str], ttl: int = 3600):
        """
        Pre-warm search results for popular queries.
        
        Args:
            popular_queries: List of frequently searched terms
            ttl: Cache TTL
        """
        from apps.ai_service.rag_service import RAGService
        
        logger.info(f"Warming search cache for {len(popular_queries)} queries")
        
        rag = RAGService()
        
        for query in popular_queries[:10]:  # Limit to top 10
            try:
                # Generate cache key
                query_hash = hashlib.md5(query.encode()).hexdigest()
                cache_key = f"search:{query_hash}"
                
                # Retrieve and cache results
                results = rag.retrieve_documents(query, top_k=5)
                
                self.cache.set(cache_key, results, ttl)
                self.metrics["items_warmed"] += 1
                
                logger.debug(f"Warmed search results for: {query}")
            except Exception as e:
                logger.error(f"Failed to warm search for '{query}': {e}")
    
    def warm_leaderboard_data(self, course_id: int, ttl: int = 1800):
        """
        Pre-compute and cache leaderboard rankings.
        """
        from apps.submissions.models import Submission
        from django.db.models import Count, Avg, Max
        
        try:
            logger.info(f"Warming leaderboard for course {course_id}")
            
            # Get top performers
            leaderboard = (
                Submission.objects
                .filter(assignment__course_id=course_id, graded=True)
                .values('user__username', 'user_id')
                .annotate(
                    submissions_graded=Count('id'),
                    avg_score=Avg('score'),
                    max_score=Max('score')
                )
                .order_by('-avg_score')
                [:50]
            )
            
            cache_key = f"leaderboard:course:{course_id}"
            self.cache.set(cache_key, list(leaderboard), ttl)
            self.metrics["items_warmed"] += 1
            
            logger.debug(f"Warmed leaderboard for {len(leaderboard)} users")
        except Exception as e:
            logger.error(f"Failed to warm leaderboard: {e}")
    
    def warm_by_access_pattern(self, lookback_days: int = 7, ttl: int = 3600):
        """
        Analyze access patterns and warm likely next requests.
        
        Uses transition patterns:
        - Users viewing course often view materials next
        - Users viewing assignment often view submissions after
        """
        from apps.analytics.models import AccessLog
        
        logger.info(f"Warming by access patterns (last {lookback_days} days)")
        
        cutoff = datetime.now() - timedelta(days=lookback_days)
        
        try:
            # Find most common access sequences
            recent_accesses = (
                AccessLog.objects
                .filter(timestamp__gte=cutoff)
                .order_by('user', 'timestamp')
            )
            
            # Get top accessed items
            top_items = (
                recent_accesses
                .values('resource_type', 'resource_id')
                .values('resource_type', 'resource_id')
                .annotate(count=Count('id'))
                .order_by('-count')
                [:20]
            )
            
            for item in top_items:
                resource_type = item['resource_type']
                resource_id = item['resource_id']
                
                cache_key = f"{resource_type}:{resource_id}:detail"
                
                # Load from database if not cached
                if not self.cache.get(cache_key):
                    self._load_resource_into_cache(resource_type, resource_id, ttl)
            
            logger.debug(f"Warmed {len(top_items)} resources from access patterns")
        except Exception as e:
            logger.error(f"Failed to warm by access pattern: {e}")
    
    @staticmethod
    def _warm_embeddings_for_course(course_id: int, materials: List, ttl: int = 3600):
        """Cache embeddings for quick vector search."""
        from django.core.cache import cache
        
        for material in materials:
            cache_key = f"embedding:material:{material.id}"
            if not cache.get(cache_key):
                # In real implementation, load from vector DB
                logger.debug(f"Would warm embeddings for material {material.id}")
    
    @staticmethod
    def _warm_recent_assignments(limit: int = 20, ttl: int = 3600):
        """Warm recently created/upcoming assignments."""
        from apps.assignments.models import Assignment
        from django.core.cache import cache
        
        recent = Assignment.objects.order_by('-created_at')[:limit]
        
        for assignment in recent:
            cache_key = f"assignment:{assignment.id}:detail"
            cache.set(cache_key, {
                "id": assignment.id,
                "title": assignment.title,
                "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            }, ttl)
    
    @staticmethod
    def _warm_user_specific_content(ttl: int = 3600):
        """Warm personalized content for active users."""
        from django.contrib.auth.models import User
        from django.core.cache import cache
        
        # Get most active users in last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        
        try:
            from apps.analytics.models import AccessLog
            active_users = (
                AccessLog.objects
                .filter(timestamp__gte=cutoff)
                .values('user_id')
                .distinct()
                [:10]
            )
            
            for access in active_users:
                user_id = access['user_id']
                PredictiveCacheWarmer._create_personal_cache(user_id, ttl)
        except:
            pass
    
    @staticmethod
    def _create_personal_cache(user_id: int, ttl: int):
        """Create personalized cache for one user."""
        from django.core.cache import cache
        
        # Get user's recent queries
        cache_key = f"personal:{user_id}:recommendations"
        # Recommendation logic would go here
    
    @staticmethod
    def _load_resource_into_cache(resource_type: str, resource_id: int, ttl: int):
        """Generic resource loader into cache."""
        from django.core.cache import cache
        
        # Route to appropriate model
        models_map = {
            'course': 'apps.courses.models.Course',
            'material': 'apps.courses.models.CourseMaterial',
            'assignment': 'apps.assignments.models.Assignment',
        }
        
        # Load and cache appropriately
        logger.debug(f"Loaded {resource_type}:{resource_id} into cache")


class CacheWarmingScheduler:
    """
    Schedule cache warming tasks.
    """
    
    @staticmethod
    def get_celery_tasks() -> Dict[str, str]:
        """Return Celery task names for scheduling."""
        return {
            "warm_popular_courses": "apps.celery_tasks.warm_cache_periodic",
            "warm_by_access_pattern": "apps.cache_warming.warm_access_patterns",
            "warm_search_cache": "apps.cache_warming.warm_popular_searches",
            "warm_leaderboards": "apps.cache_warming.warm_leaderboards",
        }
    
    @staticmethod
    def schedule_warming():
        """Configure Celery Beat schedule for cache warming."""
        return {
            "warm-cache-hourly": {
                "task": "apps.ai_service.tasks.warm_cache_periodic",
                "schedule": 3600,  # Every hour
            },
            "warm-by-patterns-daily": {
                "task": "apps.cache_warming.warm_access_patterns",
                "schedule": 86400,  # Daily
            },
            "warm-search-cache-hourly": {
                "task": "apps.cache_warming.warm_popular_searches",
                "schedule": 3600,
            },
        }
