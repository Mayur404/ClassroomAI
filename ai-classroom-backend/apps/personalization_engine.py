"""
Advanced personalization engine: learns user preferences, optimizes recommendations
"""
import logging
import hashlib
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import json
import numpy as np

from django.db import models
from django.utils import timezone
from django.db.models import Count, Avg, Q

logger = logging.getLogger(__name__)


# ============================================================================
# USER PREFERENCE MODELS
# ============================================================================

class UserPreferenceProfile(models.Model):
    """
    Stores learned user preferences and personalization data.
    """
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='preference_profile')
    
    # Learning preferences
    preferred_topics = models.JSONField(default=list)  # ["biology", "ecology", ...]
    learning_style = models.CharField(
        max_length=20,
        choices=[
            ("visual", "Visual"),
            ("auditory", "Auditory"),
            ("reading", "Reading/Writing"),
            ("kinesthetic", "Kinesthetic"),
        ],
        null=True
    )
    
    # Performance metrics
    avg_assignment_score = models.FloatField(default=0)
    total_assignments_completed = models.IntegerField(default=0)
    preferred_difficulty = models.CharField(  # Based on performance
        max_length=20,
        choices=[
            ("easy", "Easy"),
            ("medium", "Medium"),
            ("hard", "Hard"),
            ("adaptive", "Adaptive (mix)"),
        ],
        default="adaptive"
    )
    
    # Engagement metrics
    peak_activity_hour = models.IntegerField(null=True)  # 0-23
    avg_session_duration_mins = models.FloatField(default=0)
    preferred_content_types = models.JSONField(default=dict)  # {"pdf": 0.5, "video": 0.3, ...}
    
    # Recommendation state
    last_recommendations_generated = models.DateTimeField(null=True)
    recommendation_feedback_score = models.FloatField(default=0.5)  # 0-1
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences for {self.user.username}"


class UserInteractionLog(models.Model):
    """
    Log of user interactions for learning preferences.
    """
    class InteractionType(models.TextChoices):
        VIEW = "view", "Viewed"
        READ = "read", "Read"
        WATCH = "watch", "Watched"
        CLICK = "click", "Clicked"
        SEARCH = "search", "Searched"
        SUBMIT = "submit", "Submitted"
        REVIEW = "review", "Reviewed"
    
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    resource_type = models.CharField(max_length=50)  # "course", "material", "assignment", etc.
    resource_id = models.IntegerField()
    duration_seconds = models.IntegerField(null=True)  # How long spent on resource
    rating = models.IntegerField(null=True)  # 1-5 star rating if provided
    success = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['interaction_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username}: {self.interaction_type} -> {self.resource_type}"


# ============================================================================
# PERSONALIZATION ENGINE
# ============================================================================

class PersonalizationEngine:
    """
    Advanced personalization engine that learns user preferences and optimizes recommendations.
    """
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        try:
            self.user = __import__('django.contrib.auth.models', fromlist=['User']).User.objects.get(id=user_id)
            self.profile, _ = UserPreferenceProfile.objects.get_or_create(user=self.user)
        except:
            self.profile = None
    
    def learn_from_interaction(self, 
                              interaction_type: str,
                              resource_type: str,
                              resource_id: int,
                              duration_seconds: int = None,
                              rating: int = None,
                              success: bool = True):
        """
        Record user interaction and learn from it.
        """
        if not self.profile:
            return
        
        # Log interaction
        UserInteractionLog.objects.create(
            user=self.user,
            interaction_type=interaction_type,
            resource_type=resource_type,
            resource_id=resource_id,
            duration_seconds=duration_seconds,
            rating=rating,
            success=success
        )
        
        # Update learning
        self._update_preferences_from_interaction(
            interaction_type, resource_type, duration_seconds, rating
        )
    
    def get_personalized_recommendations(self, 
                                        context: str = "general",
                                        limit: int = 10) -> List[Dict]:
        """
        Get personalized recommendations based on learned preferences.
        
        Contexts:
        - "general": Mixed recommendations
        - "similar": Similar to recently viewed
        - "improve": Focus on weak areas
        - "explore": New content matching interests
        """
        if not self.profile:
            return []
        
        logger.info(f"Generating {context} recommendations for user {self.user_id}")
        
        if context == "similar":
            return self._get_similar_recommendations()
        elif context == "improve":
            return self._get_improvement_recommendations()
        elif context == "explore":
            return self._get_exploration_recommendations()
        else:
            return self._get_general_recommendations(limit)
    
    def _get_general_recommendations(self, limit: int = 10) -> List[Dict]:
        """
        General recommendations mixing different types of content.
        """
        recommendations = []
        
        # Get user's enrolled courses
        from apps.courses.models import Course, CourseMaterial
        courses = self.user.courses.all()[:3]
        
        for course in courses:
            # Get highly-rated materials from course
            materials = (
                CourseMaterial.objects
                .filter(course=course, indexed_at=True)
                .annotate(rating_count=Count('ratings'))
                .order_by('-rating_count')
                [:int(limit / len(courses))]
            )
            
            for material in materials:
                recommendations.append({
                    "type": "material",
                    "id": material.id,
                    "title": material.title,
                    "course": course.title,
                    "relevance_score": 0.8,
                    "reason": "Popular in your courses"
                })
        
        return recommendations[:limit]
    
    def _get_similar_recommendations(self) -> List[Dict]:
        """
        Recommend content similar to what user recently viewed.
        """
        # Get recently viewed materials
        recent = UserInteractionLog.objects.filter(
            user=self.user,
            interaction_type=UserInteractionLog.InteractionType.VIEW,
            resource_type='material',
            created_at__gte=timezone.now() - timedelta(days=7)
        ).order_by('-created_at')[:5]
        
        if not recent:
            return []
        
        # Extract topics from recent materials
        topics = []
        for interaction in recent:
            # In real implementation, extract topics from material
            topics.append(f"topic_{interaction.resource_id % 10}")
        
        # Find similar content
        recommendations = []
        from apps.courses.models import CourseMaterial
        
        similar = (
            CourseMaterial.objects
            .filter(topic__in=topics)
            .exclude(id__in=[r.resource_id for r in recent])
            .annotate(matches=Count('topic'))
            .order_by('-matches')[:10]
        )
        
        for material in similar:
            recommendations.append({
                "type": "material",
                "id": material.id,
                "title": material.title,
                "relevance_score": min(0.95, material.matches / len(topics)),
                "reason": "Similar to materials you viewed"
            })
        
        return recommendations
    
    def _get_improvement_recommendations(self) -> List[Dict]:
        """
        Recommend content to help improve weak areas.
        """
        # Get assignments with low scores
        from apps.submissions.models import Submission
        
        low_performing = (
            Submission.objects
            .filter(user=self.user, score__lt=70)
            .values('assignment__topic')
            .annotate(avg_score=Avg('score'))
            .order_by('avg_score')[:3]
        )
        
        recommendations = []
        from apps.courses.models import CourseMaterial
        
        for performance in low_performing:
            topic = performance['assignment__topic']
            
            # Get materials for this topic
            materials = (
                CourseMaterial.objects
                .filter(topic=topic, indexed_at=True)
                .order_by('-quality_score')[:3]
            )
            
            difficulty = 1.0 - (performance['avg_score'] / 100)  # Adaptive difficulty
            
            for material in materials:
                recommendations.append({
                    "type": "material",
                    "id": material.id,
                    "title": material.title,
                    "topic": topic,
                    "relevance_score": difficulty,
                    "reason": f"Help improve your score in {topic}"
                })
        
        return recommendations
    
    def _get_exploration_recommendations(self) -> List[Dict]:
        """
        Recommend new content that matches interests but differs from usual.
        """
        recommendations = []
        
        # Get user's preferred topics
        preferred = self.profile.preferred_topics[:3]
        
        # Find complementary topics (similar but not exact match)
        from apps.courses.models import CourseMaterial
        
        explore = (
            CourseMaterial.objects
            .filter(topic__in=preferred, indexed_at=True)
            .exclude(
                id__in=UserInteractionLog.objects
                .filter(user=self.user, resource_type='material')
                .values_list('resource_id', flat=True)
            )
            .order_by('-extraction_quality_score')[:10]
        )
        
        for material in explore:
            recommendations.append({
                "type": "material",
                "id": material.id,
                "title": material.title,
                "relevance_score": 0.7,
                "reason": "Explore new content in your interests"
            })
        
        return recommendations
    
    def get_optimal_difficulty(self) -> str:
        """
        Determine optimal difficulty level for assignments.
        """
        if not self.profile:
            return "medium"
        
        avg_score = self.profile.avg_assignment_score
        
        if avg_score < 50:
            return "easy"
        elif avg_score < 70:
            return "medium"
        elif avg_score < 85:
            return "hard"
        else:
            return "expert"
    
    def predict_study_time_needed(self, assignment_id: int) -> int:
        """
        Predict how long user will need to complete assignment.
        Based on past performance and learning speed.
        """
        from apps.submissions.models import Submission
        
        past_submissions = Submission.objects.filter(
            user=self.user,
            graded=True
        ).order_by('-created_at')[:10]
        
        if not past_submissions:
            return 30  # Default 30 minutes
        
        avg_time = sum(
            s.submission_time_minutes for s in past_submissions
            if hasattr(s, 'submission_time_minutes')
        ) / len(past_submissions)
        
        return max(10, int(avg_time))  # At least 10 minutes
    
    def should_recommend_break(self) -> bool:
        """
        Recommendation algorithm for break time (user engagement).
        """
        recent_interactions = UserInteractionLog.objects.filter(
            user=self.user,
            created_at__gte=timezone.now() - timedelta(minutes=60)
        ).count()
        
        if recent_interactions > 15:  # Very active
            return True
        
        return False
    
    def get_congrats_message(self) -> str:
        """
        Generate personalized congratulations message on achievement.
        """
        avg_score = self.profile.avg_assignment_score
        completed = self.profile.total_assignments_completed
        
        messages = [
            f"Amazing work! You've completed {completed} assignments.",
            f"Your average score is {avg_score:.0f}% - keep it up!",
            f"You're making great progress in this course.",
            f"Your learning streak is impressive!",
        ]
        
        return messages[hash(self.user.id) % len(messages)]
    
    def _update_preferences_from_interaction(self,
                                           interaction_type: str,
                                           resource_type: str,
                                           duration_seconds: int = None,
                                           rating: int = None):
        """
        Update profile preferences based on interaction.
        """
        profile = self.profile
        
        # Update content type preferences
        if resource_type not in profile.preferred_content_types:
            profile.preferred_content_types[resource_type] = 0
        
        # Increase preference score based on duration and rating
        if duration_seconds:
            boost = min(duration_seconds / 300, 0.5)  # Up to 0.5
            profile.preferred_content_types[resource_type] += boost
        
        if rating and rating >= 4:
            profile.preferred_content_types[resource_type] += 0.3
        
        # Normalize scores
        total = sum(profile.preferred_content_types.values())
        if total > 0:
            for key in profile.preferred_content_types:
                profile.preferred_content_types[key] /= total
        
        profile.updated_at = timezone.now()
        profile.save(update_fields=['preferred_content_types', 'updated_at'])


# ============================================================================
# BATCH PERSONALIZATION TASKS
# ============================================================================

def update_all_user_preferences():
    """
    Celery task: Update preferences for all active users.
    Run periodically (daily).
    """
    from django.contrib.auth.models import User
    
    active_users = User.objects.filter(
        last_login__gte=timezone.now() - timedelta(days=7)
    )
    
    logger.info(f"Updating preferences for {active_users.count()} active users")
    
    for user in active_users:
        try:
            engine = PersonalizationEngine(user.id)
            
            # Recalculate average score
            from apps.submissions.models import Submission
            submissions = Submission.objects.filter(user=user, graded=True)
            
            if submissions:
                avg_score = submissions.aggregate(Avg('score'))['score__avg']
                engine.profile.avg_assignment_score = avg_score
                engine.profile.total_assignments_completed = submissions.count()
                engine.profile.updated_at = timezone.now()
                engine.profile.save(update_fields=[
                    'avg_assignment_score',
                    'total_assignments_completed',
                    'updated_at'
                ])
        except Exception as e:
            logger.error(f"Failed to update preferences for user {user.id}: {e}")


# ============================================================================
# REST API ENDPOINTS FOR PERSONALIZATION
# ============================================================================

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recommendations(request):
    """
    GET /api/recommendations/ 
    
    Query params:
    - context: general, similar, improve, explore
    - limit: number of recommendations (default 10)
    """
    context = request.query_params.get('context', 'general')
    limit = int(request.query_params.get('limit', 10))
    
    engine = PersonalizationEngine(request.user.id)
    recommendations = engine.get_personalized_recommendations(context, limit)
    
    return Response({
        "context": context,
        "count": len(recommendations),
        "recommendations": recommendations
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def log_interaction(request):
    """
    POST /api/interactions/log/
    
    Log user interaction for learning.
    {
        "interaction_type": "view",
        "resource_type": "material",
        "resource_id": 123,
        "duration_seconds": 300,
        "rating": 5
    }
    """
    engine = PersonalizationEngine(request.user.id)
    
    engine.learn_from_interaction(
        interaction_type=request.data.get('interaction_type'),
        resource_type=request.data.get('resource_type'),
        resource_id=request.data.get('resource_id'),
        duration_seconds=request.data.get('duration_seconds'),
        rating=request.data.get('rating'),
    )
    
    return Response({
        "status": "logged",
        "interaction": request.data
    })
