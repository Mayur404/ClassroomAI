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
        message_id: int = None
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
            
            # Get relevant documents (list of strings)
            relevant_chunks = search_course(
                course_id=course.id,
                query=question,
                top_k=5
            )
            
            response_text = ""
            
            if not relevant_chunks:
                # Fallback if no documents found
                yield self._format_event('info', {
                    'message': 'No relevant documents found, using fallback'
                })
                fallback_answer = self.fallback_generator.get_fallback_answer(
                    question=question,
                    course=course,
                    chunks=[]
                )
                response_text = fallback_answer
                for token in fallback_answer.split():
                    yield self._format_event('token', {'text': token + ' '})
            else:
                # Try to stream tokens from LLM
                token_count = 0
                try:
                    # Attempt to use Ollama
                    import requests
                    from django.conf import settings
                    
                    # Build prompt with context
                    system_prompt = self._build_system_prompt(
                        course=course,
                        chunks=relevant_chunks,
                        context=context_str
                    )
                    
                    # Direct HTTP call to Ollama to be safer than the library
                    payload = {
                        "model": settings.OLLAMA_MODEL_PRIMARY,
                        "prompt": question,
                        "system": system_prompt,
                        "stream": True,
                        "options": {
                            "num_ctx": 4096,
                            "temperature": 0.2,
                        }
                    }
                    
                    ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
                    resp = requests.post(ollama_url, json=payload, stream=True, timeout=120)
                    resp.raise_for_status()
                    
                    for line in resp.iter_lines():
                        if line:
                            chunk_data = json.loads(line)
                            token = chunk_data.get('response', '')
                            if token:
                                response_text += token
                                token_count += 1
                                yield self._format_event('token', {
                                    'text': token,
                                    'token_count': token_count
                                })
                            if chunk_data.get('done'):
                                break
                                
                except Exception as e:
                    # Fallback if ollama fails or not installed
                    logger.warning(f"LLM generation failed: {str(e)}")
                    
                    yield self._format_event('info', {
                        'message': 'LLM unavailable, extracting relevant parts...'
                    })
                    
                    fallback_answer = self.fallback_generator.get_fallback_answer(
                        question=question,
                        course=course,
                        chunks=relevant_chunks
                    )
                    response_text = fallback_answer
                    # Yield in small chunks to simulate streaming
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
                        # Sources are just chunks here
                        message_obj.sources = [
                            {'text': chunk[:200], 'index': i}
                            for i, chunk in enumerate(relevant_chunks)
                        ]
                        message_obj.save(update_fields=['ai_response', 'sources'])
                    except Exception as e:
                        logger.error(f"Failed to update chat message: {e}")
                
                # Yield sources metadata
                yield self._format_event('sources', {
                    'documents': [
                        {
                            'name': f"Source {i+1}",
                            'snippet': chunk[:150],
                            'num_chunks': len(relevant_chunks),
                        }
                        for i, chunk in enumerate(relevant_chunks[:3])
                    ]
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
        event_data = {
            'type': event_type,
            'timestamp': timezone.now().isoformat(),
            **data
        }
        json_str = json.dumps(event_data)
        return f"data: {json_str}\n\n"
    
    def _build_system_prompt(self, course, chunks, context: str = "") -> str:
        """Build system prompt with course context."""
        prompt = f"""You are an expert AI teacher for '{course.name}'.
Answer ONLY using the provided materials. If unsure, say you don't know.

Materials:
"""
        for i, chunk in enumerate(chunks[:3], 1):
            prompt += f"[{i}] {chunk}\n\n"
        
        if context:
            prompt += f"\nRecent Context:\n{context}\n"
        
        prompt += "\nAnswer the student question clearly."
        return prompt


def stream_response_to_sse(course_id, question, user=None, include_context=True, message_id=None):
    """Public function to stream response as SSE."""
    generator = StreamingAnswerGenerator()
    yield from generator.stream_question_answer(
        course_id=course_id,
        question=question,
        user=user,
        include_context=include_context,
        message_id=message_id
    )
