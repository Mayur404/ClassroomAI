"""
Adaptive assignment difficulty system.
Automatically adjusts assignment difficulty based on student performance.
"""

import logging
from typing import List, Dict, Optional
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import timedelta

from apps.assignments.models import Assignment
from apps.submissions.models import Submission
from apps.chat.models import ChatMessage

logger = logging.getLogger(__name__)


class AdaptiveDifficultyService:
    """Manages adaptive difficulty for assignments."""
    
    DIFFICULTY_LEVELS = ['BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT']
    PERFORMANCE_THRESHOLD = {
        'HIGH': 85,      # Excellent performance
        'GOOD': 70,      # Good performance
        'AVERAGE': 50,   # Average performance
        'POOR': 30,      # Poor performance
        'NONE': 0,       # No submissions yet
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_student_performance(self, student, course) -> Dict:
        """
        Calculate student performance metrics.
        
        Returns:
        {
            "average_score": 85.5,
            "recent_performance": "GOOD",
            "assignment_count": 5,
            "submission_count": 4,
            "question_quality": 4.2,
            "struggle_topics": ["inheritance", "polymorphism"],
        }
        """
        # Get assignment performance
        submissions = Submission.objects.filter(
            assignment__course=course,
            student=student
        )
        
        assignment_count = Assignment.objects.filter(course=course).count()
        submission_count = submissions.count()
        
        avg_score = submissions.aggregate(Avg('ai_grade'))['ai_grade__avg'] or 0
        
        # Calculate recent performance (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_submissions = submissions.filter(submitted_at__gte=thirty_days_ago)
        recent_avg = recent_submissions.aggregate(Avg('ai_grade'))['ai_grade__avg'] or 0
        
        # Determine performance level
        performance_level = self._get_performance_level(recent_avg if recent_avg else avg_score)
        
        # Get question quality (based on helpful feedback)
        messages = ChatMessage.objects.filter(student=student, course=course)
        helpful = messages.filter(feedback_score=1).count()
        total_feedback = messages.filter(feedback_score__isnull=False).count()
        question_quality = (helpful / max(total_feedback, 1) * 5) if total_feedback else 3
        
        # Get struggle topics
        struggle_topics = self._get_struggle_topics(student, course)
        
        return {
            "average_score": round(avg_score, 1),
            "recent_performance": performance_level,
            "assignment_count": assignment_count,
            "submission_count": submission_count,
            "question_quality": round(question_quality, 1),
            "struggle_topics": struggle_topics,
        }
    
    def recommend_next_difficulty(self, student, course) -> Dict:
        """
        Recommend difficulty level for next assignment.
        
        Returns:
        {
            "recommended_difficulty": "INTERMEDIATE",
            "reason": "Student showing good performance; ready for challenge",
            "confidence": 0.85,
            "alternative_difficulty": "BEGINNER",
            "estimated_completion_time": 45,  # minutes
        }
        """
        performance = self.get_student_performance(student, course)
        
        current_level = self._get_current_assignment_difficulty(student, course)
        current_idx = self.DIFFICULTY_LEVELS.index(current_level) if current_level in self.DIFFICULTY_LEVELS else 0
        
        # Determine next level based on performance
        recent_perf = performance["recent_performance"]
        
        if recent_perf == "GOOD":  # >=70%
            # Ready to move up
            next_idx = min(current_idx + 1, len(self.DIFFICULTY_LEVELS) - 1)
            reason = "Student showing good performance; ready for challenge"
            confidence = 0.85
        elif recent_perf == "HIGH":  # >=85%
            # Move up faster
            next_idx = min(current_idx + 2, len(self.DIFFICULTY_LEVELS) - 1)
            reason = "Excellent performance; recommend accelerated progression"
            confidence = 0.95
        elif recent_perf == "AVERAGE":  # 50-70%
            # Stay at current level
            next_idx = current_idx
            reason = "Student needs more practice at current level"
            confidence = 0.70
        else:  # POOR
            # Move down or stay
            next_idx = max(current_idx - 1, 0)
            reason = "Student struggling; recommend review of fundamentals"
            confidence = 0.80
        
        recommended = self.DIFFICULTY_LEVELS[next_idx]
        alternative = self.DIFFICULTY_LEVELS[max(0, next_idx - 1)]
        
        # Estimate completion time
        completion_time = self._estimate_completion_time(recommended, performance)
        
        return {
            "recommended_difficulty": recommended,
            "reason": reason,
            "confidence": confidence,
            "alternative_difficulty": alternative,
            "estimated_completion_time": completion_time,
        }
    
    def get_difficulty_for_student(self, student, course) -> str:
        """
        Get the current recommended difficulty for a student in a course.
        
        Args:
            student: User object
            course: Course object
        
        Returns:
            Difficulty level string (BEGINNER, INTERMEDIATE, ADVANCED, EXPERT)
        """
        performance = self.get_student_performance(student, course)
        recommendation = self.recommend_next_difficulty(student, course)
        
        return recommendation["recommended_difficulty"]
    
    def get_assignment_recommendations(self, student, course, limit: int = 5) -> List[Dict]:
        """
        Get recommended assignments for student based on difficulty and struggles.
        
        Returns:
        [
            {
                "assignment_id": 1,
                "title": "Object-Oriented Programming",
                "difficulty": "INTERMEDIATE",
                "relevance_score": 0.85,
                "reason": "Addresses your struggle area: inheritance",
                "estimated_time": 45,
            }
        ]
        """
        performance = self.get_student_performance(student, course)
        recommended_difficulty = self._get_recommended_difficulty(performance)
        struggle_topics = set(performance["struggle_topics"])
        
        # Get assignments near recommended difficulty
        assignments = Assignment.objects.filter(
            course=course
        ).order_by('-created_at')
        
        recommendations = []
        
        for assignment in assignments:
            # Skip already completed
            if Submission.objects.filter(
                student=student,
                assignment=assignment,
                status='SUBMITTED'
            ).exists():
                continue
            
            # Check if assignment addresses struggles
            title_lower = assignment.title.lower()
            description_lower = getattr(assignment, 'description', '').lower()
            full_text = title_lower + ' ' + description_lower
            
            relevance = 0
            for topic in struggle_topics:
                if topic.lower() in full_text:
                    relevance += 0.3
            
            # Check difficulty match
            if hasattr(assignment, 'difficulty') and assignment.difficulty == recommended_difficulty:
                relevance += 0.5
            
            if relevance > 0:
                recommendations.append({
                    "assignment_id": assignment.id,
                    "title": assignment.title,
                    "difficulty": getattr(assignment, 'difficulty', 'INTERMEDIATE'),
                    "relevance_score": min(relevance, 1.0),
                    "reason": self._get_recommendation_reason(
                        performance,
                        getattr(assignment, 'difficulty', recommended_difficulty),
                        struggle_topics,
                        full_text
                    ),
                    "estimated_time": getattr(assignment, 'estimated_time', 45),
                })
        
        # Sort by relevance
        recommendations.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return recommendations[:limit]
    
    def estimate_learning_path(self, student, course) -> List[Dict]:
        """
        Generate a personalized learning path for the student.
        
        Returns learners should work through assignments in order based on:
        1. Current performance level
        2. Struggle areas
        3. Learning pace
        
        Returns:
        [
            {
                "week": 1,
                "assignment_ids": [1, 2, 3],
                "focus_areas": ["basics", "variables"],
                "difficulty_level": "BEGINNER",
            }
        ]
        """
        performance = self.get_student_performance(student, course)
        all_assignments = list(Assignment.objects.filter(
            course=course
        ).order_by('created_at'))
        
        if not all_assignments:
            return []
        
        # Group by estimated difficulty (simplified)
        by_difficulty = {level: [] for level in self.DIFFICULTY_LEVELS}
        for assignment in all_assignments:
            diff = getattr(assignment, 'difficulty', 'INTERMEDIATE')
            if diff in by_difficulty:
                by_difficulty[diff].append(assignment)
        
        learning_path = []
        current_week = 1
        current_difficulty_idx = 0
        
        # Start from appropriate level
        if performance["recent_performance"] in ["GOOD", "HIGH"]:
            current_difficulty_idx = 1
        elif performance["recent_performance"] == "POOR":
            current_difficulty_idx = -1
        
        # Build path
        while current_difficulty_idx < len(self.DIFFICULTY_LEVELS):
            difficulty = self.DIFFICULTY_LEVELS[current_difficulty_idx]
            assignments_at_level = by_difficulty[difficulty]
            
            if not assignments_at_level:
                current_difficulty_idx += 1
                continue
            
            # Take 2-3 assignments per week
            for i in range(0, len(assignments_at_level), 2):
                week_assignments = assignments_at_level[i:i+2]
                
                learning_path.append({
                    "week": current_week,
                    "assignment_ids": [a.id for a in week_assignments],
                    "difficulty_level": difficulty,
                    "focus_areas": self._get_focus_areas(week_assignments),
                })
                
                current_week += 1
                
                if current_week > 16:  # Max 16 weeks
                    break
            
            if current_week > 16:
                break
            
            current_difficulty_idx += 1
        
        return learning_path
    
    # Helper methods
    
    def _get_performance_level(self, score: float) -> str:
        """Convert score to performance level."""
        if score >= self.PERFORMANCE_THRESHOLD['HIGH']:
            return 'HIGH'
        elif score >= self.PERFORMANCE_THRESHOLD['GOOD']:
            return 'GOOD'
        elif score >= self.PERFORMANCE_THRESHOLD['AVERAGE']:
            return 'AVERAGE'
        elif score > self.PERFORMANCE_THRESHOLD['NONE']:
            return 'POOR'
        else:
            return 'NONE'
    
    def _get_current_assignment_difficulty(self, student, course) -> str:
        """Get average difficulty of student's current assignments."""
        submissions = Submission.objects.filter(
            student=student,
            assignment__course=course,
            status='SUBMITTED'
        ).values_list('assignment__difficulty', flat=True)
        
        if not submissions.exists():
            return 'BEGINNER'
        
        difficulties = list(submissions)
        if difficulties:
            return difficulties[-1]  # Last difficulty attempted
        
        return 'BEGINNER'
    
    def _get_struggle_topics(self, student, course, limit: int = 3) -> List[str]:
        """Identify topics the student struggles with."""
        messages = ChatMessage.objects.filter(
            student=student,
            course=course,
            role='STUDENT'
        ).order_by('-timestamp')[:50]
        
        # Simple keyword extraction from questions with low helpful ratings
        unhelpful_keywords = {}
        helpful_keywords = {}
        
        for msg in messages:
            words = msg.message.lower().split()
            
            for word in words:
                if len(word) > 5:
                    word = word.strip('.,!?;:')
                    if len(word) > 5:
                        if msg.feedback_score == -1:
                            unhelpful_keywords[word] = unhelpful_keywords.get(word, 0) + 1
                        elif msg.feedback_score == 1:
                            helpful_keywords[word] = helpful_keywords.get(word, 0) + 1
        
        # Find topics mentioned more in unhelpful questions
        struggles = []
        for word, count in sorted(unhelpful_keywords.items(), key=lambda x: x[1], reverse=True):
            if word not in helpful_keywords or unhelpful_keywords[word] > helpful_keywords.get(word, 0):
                struggles.append(word)
        
        return struggles[:limit]
    
    def _estimate_completion_time(self, difficulty: str, performance: Dict) -> int:
        """Estimate time to complete an assignment at given difficulty."""
        base_times = {
            'BEGINNER': 30,
            'INTERMEDIATE': 45,
            'ADVANCED': 60,
            'EXPERT': 90,
        }
        
        base_time = base_times.get(difficulty, 45)
        
        # Adjust based on student's question quality
        quality = performance.get('question_quality', 3) / 5
        
        # Higher quality = faster (better understanding)
        estimated = base_time / quality if quality > 0 else base_time
        
        return int(estimated)
    
    def _get_recommended_difficulty(self, performance: Dict) -> str:
        """Get recommended difficulty from performance."""
        perf_level = performance["recent_performance"]
        
        if perf_level == "HIGH":
            return "ADVANCED"
        elif perf_level == "GOOD":
            return "INTERMEDIATE"
        elif perf_level == "AVERAGE":
            return "BEGINNER"
        else:
            return "BEGINNER"
    
    def _get_recommendation_reason(self, performance, difficulty, struggles, text):
        """Generate reason for assignment recommendation."""
        reasons = []
        
        for struggle in struggles:
            if struggle.lower() in text:
                reasons.append(f"Addresses your struggle area: {struggle}")
                break
        
        if not reasons:
            if difficulty == performance.get("upcoming_difficulty"):
                reasons.append("Matches your recommended difficulty level")
            else:
                reasons.append("Recommended for your skill level")
        
        return reasons[0] if reasons else "Recommended assignment"
    
    def _get_focus_areas(self, assignments) -> List[str]:
        """Extract focus areas from assignments."""
        focus_areas = set()
        
        for assignment in assignments:
            title = assignment.title.lower()
            # Simple keyword extraction
            if 'loop' in title or 'iteration' in title:
                focus_areas.add('loops')
            if 'function' in title or 'method' in title:
                focus_areas.add('functions')
            if 'class' in title or 'object' in title:
                focus_areas.add('object-oriented')
            if 'data' in title or 'structure' in title:
                focus_areas.add('data structures')
        
        return list(focus_areas)[:3]
