"""
Conversation management service.
Handles summarization, export, and analysis of chat conversations.
"""

import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from django.db.models import Count, Q
from django.utils import timezone

from apps.chat.models import ChatMessage
from apps.courses.models import Course

logger = logging.getLogger(__name__)


class ConversationSummaryService:
    """Generates and manages conversation summaries."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def summarize_conversation(
        self,
        student,
        course,
        max_messages: int = None,
        use_ai: bool = False
    ) -> Dict:
        """
        Summarize a student's conversation in a course.
        
        Args:
            student: User object
            course: Course object
            max_messages: Limit to last N messages
            use_ai: Use LLM to generate smart summaries (requires Ollama)
        
        Returns:
        {
            "summary_text": "Student asked 5 questions about...",
            "key_topics": ["recursion", "arrays", "loops"],
            "helpful_percentage": 80,
            "message_count": 5,
            "time_span_days": 3,
            "main_struggles": ["understanding recursion"],
        }
        """
        messages = ChatMessage.objects.filter(
            student=student,
            course=course
        ).order_by('timestamp')
        
        if max_messages:
            messages = messages[:max_messages]
        
        if not messages.exists():
            return {
                "summary_text": "No conversation yet",
                "key_topics": [],
                "helpful_percentage": 0,
                "message_count": 0,
                "time_span_days": 0,
                "main_struggles": [],
            }
        
        # Basic stats
        student_messages = messages.filter(role='STUDENT')
        ai_messages = messages.filter(role='AI')
        helpful = messages.filter(feedback_score=1).count()
        total_feedback = messages.filter(feedback_score__isnull=False).count()
        
        # Extract topics
        topics = self._extract_topics(student_messages)
        
        # Calculate time span
        first_msg = messages.first()
        last_msg = messages.last()
        time_span = (last_msg.timestamp - first_msg.timestamp).days
        
        # Generate summary text
        summary_text = self._generate_summary_text(
            student_messages.count(),
            topics,
            helpful,
            total_feedback,
            time_span
        )
        
        # Get struggles
        struggles = self._identify_struggles(messages)
        
        return {
            "summary_text": summary_text,
            "key_topics": topics,
            "helpful_percentage": int((helpful / max(total_feedback, 1) * 100)) if total_feedback else 0,
            "message_count": len(messages),
            "time_span_days": max(time_span, 1),
            "main_struggles": struggles,
        }
    
    def export_conversation(
        self,
        student,
        course,
        format: str = 'json',
        max_messages: int = None
    ) -> str:
        """
        Export a conversation in various formats.
        
        Args:
            student: User object
            course: Course object
            format: 'json', 'markdown', 'csv', or 'text'
            max_messages: Limit to last N messages
        
        Returns:
            Formatted conversation string
        """
        messages = ChatMessage.objects.filter(
            student=student,
            course=course
        ).order_by('timestamp')
        
        if max_messages:
            messages = messages[:max_messages]
        
        if format == 'json':
            return self._export_as_json(messages)
        elif format == 'markdown':
            return self._export_as_markdown(messages, student, course)
        elif format == 'csv':
            return self._export_as_csv(messages)
        elif format == 'text':
            return self._export_as_text(messages)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def get_conversation_insights(
        self,
        student,
        course
    ) -> Dict:
        """
        Get detailed insights about a conversation.
        
        Returns:
        {
            "conversation_health_score": 0.82,
            "engagement_level": "high",
            "learning_velocity": "improving",
            "recommended_actions": ["review recursion", "practice more arrays"],
        }
        """
        messages = ChatMessage.objects.filter(
            student=student,
            course=course
        ).order_by('timestamp')
        
        if not messages.exists():
            return {
                "conversation_health_score": 0,
                "engagement_level": "none",
                "learning_velocity": "none",
                "recommended_actions": ["Start asking questions!"],
            }
        
        # Calculate health score (0-1)
        health_score = 0
        
        # Messages with feedback (engagement indicator)
        with_feedback = messages.filter(feedback_score__isnull=False).count()
        health_score += min((with_feedback / max(messages.count(), 1)) * 0.3, 0.3)
        
        # Helpful feedback ratio
        helpful = messages.filter(feedback_score=1).count()
        helpful_ratio = helpful / max(with_feedback, 1) if with_feedback else 0
        health_score += helpful_ratio * 0.4
        
        # Frequency (more is better)
        last_7_days = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        recent = messages.filter(timestamp__gte=last_7_days).count()
        health_score += min((recent / 10) * 0.3, 0.3)
        
        # Engagement level
        msg_count = messages.count()
        if msg_count > 20:
            engagement = "very high"
        elif msg_count > 10:
            engagement = "high"
        elif msg_count > 5:
            engagement = "moderate"
        elif msg_count > 0:
            engagement = "low"
        else:
            engagement = "none"
        
        # Learning velocity
        if len(messages) >= 3:
            # Compare feedback in first third vs last third
            third = len(messages) // 3
            first_third_helpful = messages[:third].filter(feedback_score=1).count()
            last_third_helpful = messages[-third:].filter(feedback_score=1).count()
            
            if last_third_helpful > first_third_helpful:
                velocity = "improving"
            elif last_third_helpful == first_third_helpful:
                velocity = "stable"
            else:
                velocity = "declining"
        else:
            velocity = "unknown"
        
        # Recommendations
        recommendations = []
        
        if helpful_ratio < 0.5:
            recommendations.append("Practice asking clearer questions")
        
        if msg_count < 5:
            recommendations.append("Ask more questions to build understanding")
        
        if recent == 0:
            recommendations.append("Engage more frequently with the course")
        
        if not recommendations:
            recommendations.append("Great progress! Keep it up")
        
        return {
            "conversation_health_score": round(health_score, 2),
            "engagement_level": engagement,
            "learning_velocity": velocity,
            "recommended_actions": recommendations,
        }
    
    # Export format methods
    
    def _export_as_json(self, messages) -> str:
        """Export messages as JSON."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": [
                {
                    "id": msg.id,
                    "timestamp": msg.timestamp.isoformat(),
                    "role": msg.role,
                    "message": msg.message if msg.role == 'STUDENT' else msg.ai_response,
                    "feedback_score": msg.feedback_score,
                    "feedback_text": msg.feedback_text,
                }
                for msg in messages
            ]
        }
        return json.dumps(data, indent=2)
    
    def _export_as_markdown(self, messages, student, course) -> str:
        """Export messages as Markdown."""
        md = f"# Conversation: {student.get_full_name() or student.username} - {course.name}\n\n"
        md += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md += f"Total Messages: {len(messages)}\n\n"
        md += "---\n\n"
        
        for msg in messages:
            timestamp = msg.timestamp.strftime('%Y-%m-%d %H:%M')
            
            if msg.role == 'STUDENT':
                md += f"## Student ({timestamp})\n\n"
                md += f"{msg.message}\n\n"
            else:
                md += f"## AI Response\n\n"
                md += f"{msg.ai_response}\n\n"
                
                if msg.feedback_score:
                    emoji = "✅" if msg.feedback_score == 1 else "❌"
                    md += f"{emoji} Feedback: {msg.feedback_text or 'No text'}\n\n"
            
            md += "---\n\n"
        
        return md
    
    def _export_as_csv(self, messages) -> str:
        """Export messages as CSV."""
        lines = ["Timestamp,Role,Message,Feedback"]
        
        for msg in messages:
            timestamp = msg.timestamp.isoformat()
            role = msg.role
            message = (msg.message if msg.role == 'STUDENT' else msg.ai_response).replace('"', '""')
            feedback = f'"{msg.feedback_score}: {msg.feedback_text}"' if msg.feedback_score else ''
            
            lines.append(f'{timestamp},{role},"{message}",{feedback}')
        
        return '\n'.join(lines)
    
    def _export_as_text(self, messages) -> str:
        """Export messages as plain text."""
        text = f"Conversation Export\n"
        text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"Total Messages: {len(messages)}\n\n"
        text += "=" * 80 + "\n\n"
        
        for msg in messages:
            timestamp = msg.timestamp.strftime('%Y-%m-%d %H:%M')
            
            if msg.role == 'STUDENT':
                text += f"[{timestamp}] STUDENT:\n"
                text += f"{msg.message}\n\n"
            else:
                text += f"[{timestamp}] AI RESPONSE:\n"
                text += f"{msg.ai_response}\n"
                
                if msg.feedback_score:
                    score_text = "Helpful" if msg.feedback_score == 1 else "Not helpful"
                    text += f"  Feedback: {score_text}\n"
                    if msg.feedback_text:
                        text += f"  Note: {msg.feedback_text}\n"
                
                text += "\n"
        
        return text
    
    # Helper methods
    
    def _extract_topics(self, student_messages) -> List[str]:
        """Extract key topics from student messages."""
        topics = {}
        
        for msg in student_messages:
            words = msg.message.lower().split()
            for word in words:
                clean_word = word.strip('.,!?;:\'"-')
                if len(clean_word) > 6:  # Meaningful words only
                    topics[clean_word] = topics.get(clean_word, 0) + 1
        
        # Return top topics
        sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_topics[:5]]
    
    def _generate_summary_text(self, q_count, topics, helpful, total_feedback, days) -> str:
        """Generate human-readable summary."""
        summary = f"Student asked {q_count} questions"
        
        if topics:
            summary += f" about {', '.join(topics[:2])}"
        
        if total_feedback:
            summary += f". {helpful}/{total_feedback} answers were helpful"
        
        if days > 0:
            summary += f" over {days} days"
        
        summary += "."
        
        return summary
    
    def _identify_struggles(self, messages) -> List[str]:
        """Identify areas where student struggles."""
        unhelpful_words = {}
        
        for msg in messages.filter(feedback_score=-1):
            words = msg.message.lower().split()
            for word in words:
                clean_word = word.strip('.,!?;:\'"-')
                if len(clean_word) > 6:
                    unhelpful_words[clean_word] = unhelpful_words.get(clean_word, 0) + 1
        
        if not unhelpful_words:
            return []
        
        sorted_words = sorted(unhelpful_words.items(), key=lambda x: x[1], reverse=True)
        return [f"struggling with {w[0]}" for w in sorted_words[:3]]
