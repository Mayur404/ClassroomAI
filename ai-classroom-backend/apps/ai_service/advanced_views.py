"""
API views for advanced features:
- Adaptive difficulty recommendations
- Conversation summaries and export  
- Feedback analysis insights
"""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.http import FileResponse
import io
from django.utils import timezone
from datetime import timedelta
import requests
from django.contrib.auth import get_user_model

from apps.courses.models import Course, StudentFlashcard
from apps.ai_service.adaptive_difficulty import AdaptiveDifficultyService
from apps.ai_service.conversation_service import ConversationSummaryService
from apps.ai_service.feedback_analysis import FeedbackAnalysisService
from apps.ai_service.rag_service import search_course
from apps.ai_service.services import call_ollama
from apps.chat.models import ChatMessage
from apps.submissions.models import Submission

User = get_user_model()


class AdaptiveDifficultyView(APIView):
    """Get adaptive difficulty recommendations for a student."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, student_id):
        """
        Get difficulty recommendations and learning path for a student.
        
        Returns:
        {
            "student_id": 123,
            "course_id": 1,
            "performance": {...},
            "recommended_difficulty": "INTERMEDIATE",
            "next_assignment_recommendations": [...],
            "learning_path": [...],
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is enrolled in course
        if not course.enrollments.filter(student=student).exists():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        service = AdaptiveDifficultyService()
        
        performance = service.get_student_performance(student, course)
        recommendation = service.recommend_next_difficulty(student, course)
        assignments = service.get_assignment_recommendations(student, course, limit=5)
        learning_path = service.estimate_learning_path(student, course)
        
        return Response({
            "student_id": student.id,
            "student_name": student.get_full_name() or student.username,
            "course_id": course.id,
            "course_name": course.name,
            "performance": performance,
            "recommended_difficulty": recommendation["recommended_difficulty"],
            "recommendation_reason": recommendation["reason"],
            "recommendation_confidence": recommendation["confidence"],
            "result": "success",
            "next_assignment_recommendations": assignments,
            "suggested_learning_path": learning_path,
        })


class ConversationSummaryView(APIView):
    """Get summaries and insights about conversations."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, student_id):
        """
        Get summary and insights for a student's conversation in a course.
        
        Query params:
        - max_messages: Limit to last N messages (optional)
        
        Returns:
        {
            "summary": {...},
            "insights": {...},
            "export_formats": [formats available],
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is enrolled in course
        if not course.enrollments.filter(student=student).exists():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        max_messages = request.query_params.get('max_messages', None)
        if max_messages:
            max_messages = int(max_messages)
        
        service = ConversationSummaryService()
        
        summary = service.summarize_conversation(student, course, max_messages=max_messages)
        insights = service.get_conversation_insights(student, course)
        
        return Response({
            "student_id": student.id,
            "student_name": student.get_full_name() or student.username,
            "course_id": course.id,
            "course_name": course.name,
            "summary": summary,
            "insights": insights,
            "export_formats": ['json', 'markdown', 'csv', 'text'],
            "export_url": f"/api/conversations/{student_id}/courses/{course_id}/export/",
        })


class ConversationExportView(APIView):
    """Export conversations in various formats."""
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id, course_id):
        """
        Export a conversation.
        
        Query params:
        - format: 'json', 'markdown', 'csv', or 'text' (default: json)
        - max_messages: Limit to last N messages (optional)
        
        Returns:
            File download or JSON
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        student = get_object_or_404(User, id=student_id)
        
        # Verify student is enrolled in course
        if not course.enrollments.filter(student=student).exists():
            return Response(
                {"detail": "Student not in this course"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        export_format = request.query_params.get('format', 'json')
        max_messages = request.query_params.get('max_messages', None)
        
        if max_messages:
            max_messages = int(max_messages)
        
        if export_format not in ['json', 'markdown', 'csv', 'text']:
            return Response(
                {"detail": f"Unknown format: {export_format}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ConversationSummaryService()
        content = service.export_conversation(
            student, course, format=export_format, max_messages=max_messages
        )
        
        # Determine file extension and content type
        extensions = {
            'json': ('json', 'application/json'),
            'markdown': ('md', 'text/markdown'),
            'csv': ('csv', 'text/csv'),
            'text': ('txt', 'text/plain'),
        }
        
        ext, content_type = extensions[export_format]
        filename = f"conversation_{student.username}_{course.id}.{ext}"
        
        # Create file-like object
        file_obj = io.BytesIO(content.encode('utf-8'))
        file_obj.seek(0)
        
        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=content_type
        )


class FeedbackAnalysisView(APIView):
    """Get feedback analysis and improvement recommendations."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        """
        Get comprehensive feedback analysis for a course.
        
        Returns:
        {
            "quality_metrics": {...},
            "problem_areas": [...],
            "patterns": {...},
            "recommendations": [...],
            "topic_difficulty": {...},
        }
        """
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        
        service = FeedbackAnalysisService()
        
        metrics = service.get_feedback_quality_metrics(course)
        problems = service.identify_problem_areas(course, limit=10)
        patterns = service.get_feedback_patterns(course)
        recommendations = service.get_improvement_recommendations(course)
        difficulties = service.calculate_topic_difficulty(course)
        
        return Response({
            "course_id": course.id,
            "course_name": course.name,
            "quality_metrics": metrics,
            "problem_areas": problems,
            "feedback_patterns": patterns,
            "improvement_recommendations": recommendations,
            "topic_difficulty": difficulties,
            "summary": {
                "overall_health": "good" if metrics["helpful_rate"] >= 0.7 else "needs_improvement",
                "areas_to_focus": [p["topic"] for p in problems[:3]],
                "priority_action": recommendations[0]["recommendation"] if recommendations else "No improvements needed",
            }
        })


class DashboardMetricsView(APIView):
    """Get all metrics for instructor dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get all dashboard metrics for user's courses.
        
        Returns:
        {
            "courses": [
                {
                    "course_id": 1,
                    "course_name": "Python 101",
                    "metrics": {...},
                }
            ],
            "aggregate_metrics": {...},
        }
        """
        courses = Course.objects.filter(teacher=request.user)
        
        feedback_service = FeedbackAnalysisService()
        
        course_data = []
        all_metrics = {
            "total_students": 0,
            "total_questions": 0,
            "average_helpful_rate": [],
        }
        
        for course in courses:
            metrics = feedback_service.get_feedback_quality_metrics(course)
            problems = feedback_service.identify_problem_areas(course, limit=3)
            
            all_metrics["total_students"] += course.enrollments.count()
            all_metrics["total_questions"] += sum(1 for _ in metrics)
            all_metrics["average_helpful_rate"].append(metrics["helpful_rate"])
            
            course_data.append({
                "course_id": course.id,
                "course_name": course.name,
                "student_count": course.enrollments.count(),
                "helpful_rate": metrics["helpful_rate"],
                "feedback_rate": metrics["feedback_rate"],
                "trend": metrics["trend"],
                "top_problem_areas": [p["topic"] for p in problems[:3]],
            })
        
        # Calculate aggregate
        if all_metrics["average_helpful_rate"]:
            avg_rate = sum(all_metrics["average_helpful_rate"]) / len(all_metrics["average_helpful_rate"])
        else:
            avg_rate = 0
        
        return Response({
            "courses": course_data,
            "aggregate": {
                "total_courses": courses.count(),
                "total_students": all_metrics["total_students"],
                "average_helpful_rate": round(avg_rate, 2),
            }
        })


class StudyToolsGenerateView(APIView):
    """Generate quiz and flashcards from uploaded course material."""
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):
        if request.user.role == "TEACHER":
            course = get_object_or_404(Course, id=course_id, teacher=request.user)
        else:
            course = get_object_or_404(Course, id=course_id, enrollments__student=request.user)

        mode = str(request.data.get("mode", "both")).strip().lower()
        if mode not in {"quiz", "flashcards", "both"}:
            mode = "both"
        if mode in {"flashcards", "both"} and request.user.role != "STUDENT":
            if mode == "flashcards":
                return Response({"detail": "Flashcards are only available for students."}, status=status.HTTP_403_FORBIDDEN)
            mode = "quiz"

        topic = str(request.data.get("topic", "")).strip()
        topics = request.data.get("topics", [])
        include_all_modules = bool(request.data.get("include_all_modules", False))
        module_scope = str(request.data.get("module_scope", "single")).strip().lower()

        normalized_topics = []
        if isinstance(topics, list):
            normalized_topics = [str(item).strip() for item in topics if str(item).strip()]

        if include_all_modules or module_scope == "all":
            schedule_topics = [
                str(item.topic).strip()
                for item in course.schedule_items.all().order_by("class_number", "order_index")
                if str(item.topic).strip()
            ]
            normalized_topics = schedule_topics or normalized_topics

        if topic:
            normalized_topics = [topic, *normalized_topics]

        deduped_topics = []
        seen = set()
        for item in normalized_topics:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped_topics.append(item)

        if not deduped_topics:
            return Response({"detail": "Select at least one topic or module."}, status=status.HTTP_400_BAD_REQUEST)

        topic_query = "; ".join(deduped_topics[:10])
        chunks = search_course(course_id=course.id, query=topic_query, top_k=10)
        context = "\n\n".join(chunks[:4]) if chunks else (course.syllabus_text or "")[:3000]
        if not context:
            return Response({"detail": "Upload and analyze materials first."}, status=status.HTTP_400_BAD_REQUEST)

        prompt = f"""
Create a compact study pack in valid JSON only.
Topic Scope: {deduped_topics}
Context:\n{context}

Schema:
{{
  "quiz": [
    {{"type":"MCQ|TRUE_FALSE|SHORT", "question":"...", "options":["..."], "answer":"...", "explanation":"..."}}
  ],
  "flashcards": [
    {{"question":"...", "answer":"..."}}
  ]
}}
Rules:
- 6 quiz items, mixed types.
- 10 flashcards.
- Keep directly grounded in provided context.
"""

        def _fallback_pack():
            import re

            cleaned = re.sub(r"\s+", " ", context).strip()
            fragments = [frag.strip() for frag in re.split(r"(?<=[.!?])\s+", cleaned) if frag.strip()]
            if not fragments:
                fragments = [cleaned] if cleaned else [f"Key concept: {', '.join(deduped_topics[:3])}."]

            quiz = []
            for idx, frag in enumerate(fragments[:6], start=1):
                quiz.append(
                    {
                        "type": "SHORT",
                        "question": f"Q{idx}: Explain this idea in your own words: {', '.join(deduped_topics[:2])}",
                        "options": [],
                        "answer": frag[:220],
                        "explanation": "Generated from course context fallback.",
                    }
                )

            flashcards = []
            for idx in range(10):
                frag = fragments[idx % len(fragments)]
                flashcards.append(
                    {
                        "question": f"{deduped_topics[idx % len(deduped_topics)]}: key point {idx + 1}?",
                        "answer": frag[:220],
                    }
                )
            return {"quiz": quiz, "flashcards": flashcards}

        import json
        try:
            raw = call_ollama(prompt, format_json=True, temperature=0.2, num_predict=1200)
            data = json.loads(raw.strip("` ").replace("json\n", "", 1)) if raw.strip().startswith("`") else json.loads(raw)
        except Exception:
            data = _fallback_pack()

        created_flashcards = []
        if mode in {"flashcards", "both"}:
            for card in data.get("flashcards", [])[:20]:
                obj = StudentFlashcard.objects.create(
                    course=course,
                    student=request.user,
                    question=str(card.get("question", "")).strip(),
                    answer=str(card.get("answer", "")).strip(),
                    due_at=timezone.now(),
                )
                created_flashcards.append(
                    {
                        "id": obj.id,
                        "question": obj.question,
                        "answer": obj.answer,
                        "due_at": obj.due_at,
                    }
                )

        quiz_payload = data.get("quiz", []) if mode in {"quiz", "both"} else []
        return Response(
            {
                "quiz": quiz_payload,
                "flashcards": created_flashcards,
                "mode": mode,
                "selected_topics": deduped_topics,
                "module_scope": "all" if include_all_modules or module_scope == "all" else ("multiple" if len(deduped_topics) > 1 else "single"),
            }
        )


class FlashcardReviewView(APIView):
    """Update SM-2 schedule after a student reviews a flashcard."""
    permission_classes = [IsAuthenticated]

    def post(self, request, flashcard_id):
        card = get_object_or_404(StudentFlashcard, id=flashcard_id, student=request.user)
        quality = int(request.data.get("quality", 0))
        if quality < 0 or quality > 5:
            return Response({"detail": "quality must be between 0 and 5"}, status=status.HTTP_400_BAD_REQUEST)

        if quality < 3:
            card.repetitions = 0
            card.interval_days = 1
        else:
            if card.repetitions == 0:
                card.interval_days = 1
            elif card.repetitions == 1:
                card.interval_days = 6
            else:
                card.interval_days = max(1, round(card.interval_days * card.ease_factor))
            card.repetitions += 1

        card.ease_factor = max(1.3, card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        card.due_at = timezone.now() + timedelta(days=card.interval_days)
        card.save(update_fields=["repetitions", "interval_days", "ease_factor", "due_at", "updated_at"])

        return Response(
            {
                "flashcard_id": card.id,
                "repetitions": card.repetitions,
                "interval_days": card.interval_days,
                "ease_factor": round(card.ease_factor, 3),
                "due_at": card.due_at,
            }
        )


class WeakTopicAnalysisView(APIView):
    """Identify weak topics from submissions and chat patterns."""
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
        messages = ChatMessage.objects.filter(course=course).order_by("-timestamp")[:250]
        submissions = Submission.objects.filter(assignment__course=course).order_by("-submitted_at")[:250]

        topic_scores = {}

        for message in messages:
            text = (message.message or "").lower()
            for token in text.split():
                token = token.strip(".,:;!?()[]{}\"'")
                if len(token) < 5:
                    continue
                entry = topic_scores.setdefault(token, {"mentions": 0, "negative": 0, "avg_score": 0.0, "count": 0})
                entry["mentions"] += 1
                if message.feedback_score == -1:
                    entry["negative"] += 1

        for sub in submissions:
            feedback = str(sub.ai_feedback or "").lower()
            for token in feedback.split():
                token = token.strip(".,:;!?()[]{}\"'")
                if len(token) < 5:
                    continue
                entry = topic_scores.setdefault(token, {"mentions": 0, "negative": 0, "avg_score": 0.0, "count": 0})
                entry["avg_score"] += float(sub.ai_grade or 0)
                entry["count"] += 1

        weak_topics = []
        for topic, data in topic_scores.items():
            if data["mentions"] < 2:
                continue
            avg_score = (data["avg_score"] / data["count"]) if data["count"] else 100.0
            risk = (data["negative"] * 4) + max(0, 70 - avg_score)
            weak_topics.append(
                {
                    "topic": topic,
                    "mentions": data["mentions"],
                    "negative_feedback": data["negative"],
                    "avg_score": round(avg_score, 2),
                    "risk_score": round(risk, 2),
                }
            )

        weak_topics.sort(key=lambda x: x["risk_score"], reverse=True)
        return Response({"weak_topics": weak_topics[:15]})


class SarvamTranslateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.conf import settings

        api_key = getattr(settings, "SARVAM_API_KEY", "")
        if not api_key:
            return Response({"detail": "SARVAM_API_KEY not configured."}, status=status.HTTP_400_BAD_REQUEST)

        text = str(request.data.get("text", "")).strip()
        target_language_code = str(request.data.get("target_language_code", "hi-IN")).strip()
        if not text:
            return Response({"detail": "text is required."}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "input": text,
            "source_language_code": "en-IN",
            "target_language_code": target_language_code,
            "speaker_gender": "Female",
            "mode": "formal",
            "model": "sarvam-translate:v1",
            "enable_preprocessing": False,
        }
        headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
        response = requests.post("https://api.sarvam.ai/translate", json=payload, headers=headers, timeout=45)
        response.raise_for_status()
        data = response.json()
        translated = data.get("translated_text") or text
        return Response({"translated_text": translated, "target_language_code": target_language_code})

