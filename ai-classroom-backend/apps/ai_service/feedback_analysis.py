"""
Advanced feedback analysis service.
Analyzes feedback patterns to improve ranking, identify issues, and optimize responses.
"""

import logging
from typing import List, Dict, Tuple
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta

from apps.chat.models import ChatMessage
from apps.courses.models import Course

logger = logging.getLogger(__name__)


class FeedbackAnalysisService:
    """Analyzes feedback patterns for system improvement."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_feedback_quality_metrics(self, course: Course) -> Dict:
        """
        Get comprehensive feedback quality metrics for a course.
        
        Returns:
        {
            "helpful_rate": 0.82,
            "feedback_rate": 0.45,
            "trend": "improving",
            "most_helpful_topics": ["inheritance", "polymorphism"],
            "most_unhelpful_topics": ["recursion"],
            "improvement_potential": 0.35,
        }
        """
        messages = ChatMessage.objects.filter(course=course)
        
        with_feedback = messages.filter(feedback_score__isnull=False)
        if not with_feedback.exists():
            return {
                "helpful_rate": 0,
                "feedback_rate": 0,
                "trend": "insufficient_data",
                "most_helpful_topics": [],
                "most_unhelpful_topics": [],
                "improvement_potential": 0,
            }
        
        helpful = with_feedback.filter(feedback_score=1).count()
        unhelpful = with_feedback.filter(feedback_score=-1).count()
        helpful_rate = helpful / max(with_feedback.count(), 1)
        
        # Feedback rate (% of messages with feedback)
        feedback_rate = with_feedback.count() / max(messages.count(), 1)
        
        # Trend (compare recent vs older)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        old_helpful = messages.filter(
            timestamp__lt=thirty_days_ago,
            feedback_score=1
        ).count()
        old_with_feedback = messages.filter(
            timestamp__lt=thirty_days_ago,
            feedback_score__isnull=False
        ).count()
        old_rate = old_helpful / max(old_with_feedback, 1) if old_with_feedback else 0
        
        if helpful_rate > old_rate:
            trend = "improving"
        elif helpful_rate < old_rate:
            trend = "declining"
        else:
            trend = "stable"
        
        # Extract topics
        helpful_topics = self._get_topics_by_feedback(course, feedback_score=1, limit=5)
        unhelpful_topics = self._get_topics_by_feedback(course, feedback_score=-1, limit=5)
        
        # Improvement potential (how much better could we be)
        improvement_potential = 1 - helpful_rate
        
        return {
            "helpful_rate": round(helpful_rate, 2),
            "feedback_rate": round(feedback_rate, 2),
            "trend": trend,
            "most_helpful_topics": helpful_topics,
            "most_unhelpful_topics": unhelpful_topics,
            "improvement_potential": round(improvement_potential, 2),
        }
    
    def identify_problem_areas(self, course: Course, limit: int = 10) -> List[Dict]:
        """
        Identify topics or question types with consistently low helpful rates.
        
        Returns:
        [
            {
                "topic": "recursion",
                "unhelpful_count": 8,
                "helpful_count": 2,
                "unhelpful_rate": 0.8,
                "severity": "critical",
                "sample_questions": ["How does recursion work?", ...],
            }
        ]
        """
        unhelpful = ChatMessage.objects.filter(
            course=course,
            feedback_score=-1
        ).order_by('-timestamp')[:100]
        
        topic_stats = {}
        
        for msg in unhelpful:
            topics = self._extract_question_topics(msg.message)
            
            for topic in topics:
                if topic not in topic_stats:
                    topic_stats[topic] = {
                        "unhelpful": 0,
                        "helpful": 0,
                        "questions": []
                    }
                
                topic_stats[topic]["unhelpful"] += 1
                topic_stats[topic]["questions"].append(msg.message)
        
        # Get corresponding helpful counts
        helpful = ChatMessage.objects.filter(
            course=course,
            feedback_score=1
        )
        
        for msg in helpful:
            topics = self._extract_question_topics(msg.message)
            
            for topic in topics:
                if topic not in topic_stats:
                    topic_stats[topic] = {
                        "unhelpful": 0,
                        "helpful": 0,
                        "questions": []
                    }
                
                topic_stats[topic]["helpful"] += 1
        
        # Rank by severity
        problems = []
        
        for topic, stats in topic_stats.items():
            total = stats["unhelpful"] + stats["helpful"]
            if total >= 3:  # Need minimum feedback count
                unhelpful_rate = stats["unhelpful"] / max(total, 1)
                
                if unhelpful_rate >= 0.5:  # More than 50% unhelpful
                    severity = "critical" if unhelpful_rate >= 0.8 else "high"
                    
                    problems.append({
                        "topic": topic,
                        "unhelpful_count": stats["unhelpful"],
                        "helpful_count": stats["helpful"],
                        "unhelpful_rate": round(unhelpful_rate, 2),
                        "severity": severity,
                        "sample_questions": stats["questions"][:3],
                    })
        
        # Sort by severity and rate
        problems.sort(key=lambda x: (x["severity"] == "critical", x["unhelpful_rate"]), reverse=True)
        
        return problems[:limit]
    
    def get_feedback_patterns(self, course: Course) -> Dict:
        """
        Analyze feedback patterns to understand user behavior.
        
        Returns:
        {
            "avg_feedback_delay": 180,  # seconds
            "feedback_correlation": {...},  # correlations between metrics
            "peak_feedback_time": "14:30",
            "feedback_volume_trend": "increasing",
        }
        """
        with_feedback = ChatMessage.objects.filter(
            course=course,
            feedback_score__isnull=False
        ).order_by('timestamp')
        
        if not with_feedback.exists():
            return {
                "avg_feedback_delay": 0,
                "feedback_correlation": {},
                "peak_feedback_time": "N/A",
                "feedback_volume_trend": "insufficient_data",
            }
        
        # Average delay between response and feedback
        delays = []
        for msg in with_feedback:
            if msg.feedback_timestamp:
                delay = (msg.feedback_timestamp - msg.timestamp).total_seconds()
                delays.append(delay)
        
        avg_delay = sum(delays) / len(delays) if delays else 0
        
        # Peak feedback time
        feedback_hours = {}
        for msg in with_feedback:
            if msg.feedback_timestamp:
                hour = msg.feedback_timestamp.hour
                feedback_hours[hour] = feedback_hours.get(hour, 0) + 1
        
        peak_hour = max(feedback_hours, key=feedback_hours.get) if feedback_hours else 0
        peak_time = f"{peak_hour:02d}:00"
        
        # Volume trend
        last_week = timezone.now() - timedelta(days=7)
        last_month = timezone.now() - timedelta(days=30)
        
        volume_last_week = with_feedback.filter(timestamp__gte=last_week).count()
        volume_last_month = with_feedback.filter(timestamp__gte=last_month).count()
        
        volume_trend = "increasing" if volume_last_week > volume_last_month / 4 else "decreasing"
        
        return {
            "avg_feedback_delay": int(avg_delay),
            "feedback_correlation": self._calculate_feedback_correlations(course),
            "peak_feedback_time": peak_time,
            "feedback_volume_trend": volume_trend,
        }
    
    def get_improvement_recommendations(self, course: Course) -> List[Dict]:
        """
        Get specific, actionable recommendations for improving answer quality.
        
        Returns:
        [
            {
                "recommendation": "Improve recursion explanations",
                "rationale": "8/10 questions about recursion marked unhelpful",
                "impact": "Could improve helpful rate by 8%",
                "priority": "high",
                "action_items": ["Add more examples", "Explain base case better"],
            }
        ]
        """
        problems = self.identify_problem_areas(course, limit=5)
        recommendations = []
        
        for problem in problems:
            if problem["severity"] == "critical":
                impact = problem["unhelpful_rate"] * 10  # Rough impact calculation
                priority = "critical"
            else:
                impact = problem["unhelpful_rate"] * 5
                priority = "high"
            
            # Generate action items
            action_items = self._generate_action_items(problem["topic"])
            
            recommendations.append({
                "recommendation": f"Improve {problem['topic']} explanations",
                "rationale": f"{problem['unhelpful_count']}/{problem['unhelpful_count'] + problem['helpful_count']} questions about {problem['topic']} marked unhelpful",
                "impact": f"Could improve helpful rate by {int(impact)}%",
                "priority": priority,
                "action_items": action_items,
            })
        
        return recommendations
    
    def calculate_topic_difficulty(self, course: Course) -> Dict[str, Dict]:
        """
        Calculate perceived difficulty of topics based on feedback patterns.
        
        Returns:
        {
            "recursion": {
                "perceived_difficulty": 0.8,
                "confidence": 0.6,
                "sample_size": 12,
            }
        }
        """
        messages = ChatMessage.objects.filter(course=course, feedback_score__isnull=False)
        
        topic_stats = {}
        
        for msg in messages:
            topics = self._extract_question_topics(msg.message)
            
            for topic in topics:
                if topic not in topic_stats:
                    topic_stats[topic] = {
                        "total": 0,
                        "unhelpful": 0,
                    }
                
                topic_stats[topic]["total"] += 1
                if msg.feedback_score == -1:
                    topic_stats[topic]["unhelpful"] += 1
        
        result = {}
        
        for topic, stats in topic_stats.items():
            if stats["total"] >= 3:  # Minimum sample
                perceived_difficulty = stats["unhelpful"] / stats["total"]
                confidence = min(stats["total"] / 20, 1.0)  # Normalize to 0-1
                
                result[topic] = {
                    "perceived_difficulty": round(perceived_difficulty, 2),
                    "confidence": round(confidence, 2),
                    "sample_size": stats["total"],
                }
        
        return result
    
    # Helper methods
    
    def _get_topics_by_feedback(self, course: Course, feedback_score: int, limit: int = 5) -> List[str]:
        """Get topics most mentioned with specific feedback."""
        messages = ChatMessage.objects.filter(
            course=course,
            feedback_score=feedback_score
        )
        
        topic_count = {}
        
        for msg in messages:
            topics = self._extract_question_topics(msg.message)
            for topic in topics:
                topic_count[topic] = topic_count.get(topic, 0) + 1
        
        sorted_topics = sorted(topic_count.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_topics[:limit]]
    
    def _extract_question_topics(self, question: str) -> List[str]:
        """Extract topic keywords from a question."""
        common_cs_terms = [
            'recursion', 'iteration', 'loop', 'array', 'list', 'dictionary',
            'class', 'object', 'function', 'method', 'inheritance', 'polymorphism',
            'encapsulation', 'abstraction', 'interface', 'exception', 'error',
            'variable', 'constant', 'operator', 'conditional', 'statement',
            'parameter', 'argument', 'return', 'type', 'casting',
            'algorithm', 'data structure', 'sorting', 'searching', 'graph',
            'tree', 'hash', 'regex', 'string', 'buffer'
        ]
        
        question_lower = question.lower()
        topics = []
        
        for term in common_cs_terms:
            if term in question_lower:
                topics.append(term)
        
        return topics
    
    def _calculate_feedback_correlations(self, course: Course) -> Dict:
        """Calculate correlations between feedback and other metrics."""
        correlations = {}
        
        # Example: correlation between response length and helpfulness
        messages = ChatMessage.objects.filter(course=course, feedback_score__isnull=False)
        
        helpful = messages.filter(feedback_score=1)
        unhelpful = messages.filter(feedback_score=-1)
        
        helpful_avg_length = helpful.aggregate(
            avg_len=Avg('ai_response__length')
        )['avg_len'] or 0
        unhelpful_avg_length = unhelpful.aggregate(
            avg_len=Avg('ai_response__length')
        )['avg_len'] or 0
        
        correlations['response_length_helpfulness'] = {
            "helpful_avg_chars": int(helpful_avg_length),
            "unhelpful_avg_chars": int(unhelpful_avg_length),
            "correlation": "positive" if helpful_avg_length > unhelpful_avg_length else "negative",
        }
        
        return correlations
    
    def _generate_action_items(self, topic: str) -> List[str]:
        """Generate specific action items for improving a topic."""
        action_map = {
            'recursion': [
                'Add visual step-through examples',
                'Explain base cases explicitly',
                'Show common recursion mistakes'
            ],
            'loop': [
                'Show different loop structures',
                'Explain loop counters clearly',
                'Provide break/continue examples'
            ],
            'inheritance': [
                'Show inheritance hierarchies visually',
                'Explain method overriding',
                'Provide real-world inheritance examples'
            ],
            'polymorphism': [
                'Explain method overloading',
                'Show interface implementations',
                'Provide factory pattern examples'
            ],
        }
        
        default_actions = [
            f'Provide more {topic} examples',
            f'Create practice problems on {topic}',
            f'Link to supplementary {topic} resources',
        ]
        
        return action_map.get(topic, default_actions)
