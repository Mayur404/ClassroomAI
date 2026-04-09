"""
Streaming response service for real-time token generation.
Enables Server-Sent Events (SSE) for token-by-token response streaming.
"""

import json
import logging
from typing import Generator, Optional, Dict, Any
from django.utils import timezone

from apps.chat.models import ChatMessage
from apps.courses.models import Course
from .services import answer_course_question
from .rag_service import search_course
from .fallback_service import FallbackAnswerGenerator
from .language_service import normalize_language_code, translate_text_with_sarvam, translate_text_with_sarvam_meta

logger = logging.getLogger(__name__)


class StreamingAnswerGenerator:
    """Handles real-time streaming of AI responses."""
    
    def __init__(self):
        self.fallback_generator = FallbackAnswerGenerator()
    
    def stream_question_answer(
        self, 
        course_id: int, 
        question: str, 
        user=None,
        include_context: bool = True,
        message_id: int = None,
        source_language_code: str = "unknown",
        target_language_code: str = "unknown",
    ) -> Generator[str, None, None]:
        """
        Stream answer to a question as tokens are generated.
        
        Yields JSON strings suitable for SSE transmission.
        """
        try:
            # Start event
            yield self._format_event('start', {
                'message': 'Generating response...',
                'timestamp': timezone.now().isoformat()
            })
            
            # Get course
            try:
                course = Course.objects.get(id=course_id)
            except Course.DoesNotExist:
                raise ValueError(f"Course {course_id} not found")
            
            # Get conversation context if requested
            context_str = ""
            if include_context and user:
                try:
                    from apps.chat.models import ChatMessage
                    recent_messages = ChatMessage.objects.filter(
                        course=course, student=user
                    ).order_by('-timestamp')[:6]
                    
                    context_messages = list(reversed(recent_messages))
                    context_parts = []
                    for msg in context_messages:
                        if msg.role == "STUDENT":
                            context_parts.append(f"Q: {msg.message}")
                        else:
                            # Use ai_response or message depending on field name
                            resp = getattr(msg, 'ai_response', msg.message)
                            context_parts.append(f"A: {resp[:200]}")
                    
                    if context_parts:
                        context_str = "\n".join(context_parts)
                except Exception as e:
                    logger.warning(f"Failed to get context: {e}")
            
            normalized_source = normalize_language_code(source_language_code, fallback="unknown")
            normalized_target = normalize_language_code(target_language_code, fallback="unknown")
            normalized_question_result = translate_text_with_sarvam_meta(
                question,
                source_language_code=normalized_source,
                target_language_code="en-IN",
            )
            english_question = normalized_question_result.get("translated_text", question)
            detected_source = normalized_question_result.get("source_language_code") or "en-IN"
            effective_target = detected_source if normalized_target == "unknown" else normalized_target
            
            response_text = ""

            try:
                result = answer_course_question(
                    course=course,
                    question=english_question,
                    user=user,
                    include_context=include_context,
                )
                
                # Check for low confidence or empty materials within premium response
                if result.get("confidence", 1.0) < 0.15:
                    yield self._format_event('info', {
                        'message': 'Low confidence in materials, using fallback'
                    })
                    
                response_text = result.get("answer", "")
                # Ensure translation back to the user's expected target language
                response_text = translate_text_with_sarvam(
                    response_text,
                    source_language_code="en-IN",
                    target_language_code=effective_target,
                )
                
                streamed_sources = result.get("sources", [])
                
                # Basic token streaming simulation
                words = response_text.split()
                for i in range(0, len(words), 3):
                    chunk = " ".join(words[i:i + 3]) + " "
                    yield self._format_event('token', {'text': chunk, 'token_count': i + 1})
                    
            except Exception as e:
                logger.warning(f"LLM generation failed: {str(e)}")
                fallback_answer = self.fallback_generator.get_fallback_answer(
                    question=english_question,
                    course=course,
                    chunks=[]
                )
                response_text = translate_text_with_sarvam(
                    fallback_answer,
                    source_language_code="en-IN",
                    target_language_code=effective_target,
                )
                streamed_sources = []
                words = fallback_answer.split()
                for i in range(0, len(words), 3):
                    chunk = " ".join(words[i:i+3]) + " "
                    yield self._format_event('token', {'text': chunk})
            
            # Update the database layer with the completed response 
            if message_id and response_text:
                from apps.chat.models import ChatMessage
                try:
                    message_obj = ChatMessage.objects.get(id=message_id)
                    message_obj.ai_response = response_text
                    
                    # Convert source objects back properly or store direct
                    message_obj.sources = streamed_sources
                    message_obj.save(update_fields=['ai_response', 'sources'])
                except Exception as e:
                    logger.error(f"Failed to update chat message: {e}")
            
            # Yield sources metadata
            yield self._format_event('sources', {
                'documents': streamed_sources
            })
            
            # Completion event
            yield self._format_event('complete', {
                'timestamp': timezone.now().isoformat(),
                'answer': response_text
            })
            
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield self._format_event('error', {'message': f"Error: {str(e)}"})
    
    def _format_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format data as SSE event string."""
        if event_type == "token":
            event_type = "answer_chunk"
            if "text" in data and "chunk" not in data:
                data["chunk"] = data["text"]
                
        event_data = {
            'type': event_type,
            'timestamp': timezone.now().isoformat(),
            **data
        }
        json_str = json.dumps(event_data)
        return f"event: {event_type}\ndata: {json_str}\n\n"
    
    def _build_system_prompt(self, course, chunks, context: str = "") -> str:
        prompt = f"""You are an expert AI teacher for '{course.name}'.
Answer ONLY using the provided materials. If the answer is not explicitly found in the provided resources, you MUST respond with exactly: 'I couldn't find this in the resources you've provided. Please refer to your course materials or ask your instructor for clarification.' Do NOT infer or guess.

Materials:
"""
        for i, chunk in enumerate(chunks[:3], 1):
            prompt += f"[{i}] {chunk}\n\n"
        
        if context:
            prompt += f"\nRecent Context:\n{context}\n"
        
        prompt += "\nAnswer the student question clearly and strictly concisely. Keep your answer as short and direct as possible."
        return prompt


def stream_response_to_sse(
    course_id,
    question,
    user=None,
    include_context=True,
    message_id=None,
    source_language_code="en-IN",
    target_language_code="en-IN",
):
    """Public function to stream response as SSE."""
    generator = StreamingAnswerGenerator()
    yield from generator.stream_question_answer(
        course_id=course_id,
        question=question,
        user=user,
        include_context=include_context,
        message_id=message_id,
        source_language_code=source_language_code,
        target_language_code=target_language_code,
    )
