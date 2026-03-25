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
        include_context: bool = True
    ) -> Generator[str, None, None]:
        """
        Stream answer to a question as tokens are generated.
        
        Yields JSON strings containing:
        - token: Individual response token
        - type: 'token' | 'sources' | 'done' | 'error'
        - timestamp: When token was generated
        
        Args:
            course_id: Course database ID
            question: User's question
            user: User object for context retrieval
            include_context: Whether to include conversation context
        
        Yields:
            JSON strings suitable for SSE transmission
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
                            context_parts.append(f"A: {msg.ai_response[:200]}")
                    
                    if context_parts:
                        context_str = "\n".join(context_parts)
                except Exception as e:
                    logger.warning(f"Failed to get context: {e}")
            
            # Get relevant documents
            relevant_docs = search_course(
                course_id=course.id,
                query=question,
                top_k=5
            )
            
            if not relevant_docs:
                # Fallback if no documents found
                yield self._format_event('info', {
                    'message': 'No relevant documents found, using fallback'
                })
                fallback_answer = self.fallback_generator.get_fallback_answer(
                    question=question,
                    course=course
                )
                for token in fallback_answer.split():
                    yield self._format_event('token', {'text': token + ' '})
            else:
                # Stream tokens from LLM
                token_count = 0
                try:
                    # Note: This would need to be implemented in services.py
                    # For now, use the fallback approach
                    from ollama import generate
                    
                    # Build prompt with context
                    system_prompt = self._build_system_prompt(
                        course=course,
                        documents=relevant_docs,
                        context=context_str
                    )
                    
                    # Stream from Ollama
                    from django.conf import settings
                    
                    response_text = ""
                    for chunk in generate(
                        model=settings.OLLAMA_MODEL_PRIMARY,
                        prompt=question,
                        system=system_prompt,
                        stream=True,
                        keep_alive=settings.OLLAMA_EMBED_KEEP_ALIVE or "30m"
                    ):
                        if 'response' in chunk:
                            token = chunk['response']
                            response_text += token
                            token_count += 1
                            
                            # Yield token for streaming
                            yield self._format_event('token', {
                                'text': token,
                                'token_count': token_count
                            })
                except ImportError:
                    # Fallback if ollama package not found
                    logger.warning("Ollama package not available, using fallback")
                    fallback_answer = self.fallback_generator.get_fallback_answer(
                        question=question,
                        course=course
                    )
                    for token in fallback_answer.split():
                        response_text += token + " "
                        yield self._format_event('token', {'text': token + ' '})
                
                # Yield sources after response
                yield self._format_event('sources', {
                    'documents': [
                        {
                            'name': doc.get('document_name', 'Unknown'),
                            'section': doc.get('section_direct', ''),
                            'page': doc.get('page'),
                            'relevance': doc.get('relevance_score', 0)
                        }
                        for doc in relevant_docs
                    ]
                })
            
            # Completion event
            yield self._format_event('done', {'timestamp': timezone.now().isoformat()})
            
        except ValueError as e:
            yield self._format_event('error', {'message': str(e)})
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield self._format_event('error', {'message': 'Failed to generate response'})
    
    def _format_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        Format data as SSE event string.
        
        Args:
            event_type: Type of event (token, sources, done, error, etc)
            data: Event data dictionary
        
        Returns:
            SSE-formatted event string
        """
        event_data = {
            'type': event_type,
            'timestamp': timezone.now().isoformat(),
            **data
        }
        
        # Format as Server-Sent Event
        json_str = json.dumps(event_data)
        return f"data: {json_str}\n\n"
    
    def _build_system_prompt(
        self,
        course,
        documents,
        context: str = ""
    ) -> str:
        """
        Build system prompt with course context and document sources.
        
        Args:
            course: Course object
            documents: List of relevant documents
            context: Previous conversation context
        
        Returns:
            System prompt string
        """
        prompt = f"""You are an AI tutor for {course.name}.

Your role:
- Answer questions based on course materials
- Be clear and educational
- Cite specific sections when referencing materials
- Help students understand concepts deeply

Course Level: {course.level}
Prerequisites: {course.prerequisites or 'None'}

"""
        
        # Add document sources
        if documents:
            prompt += "Available course materials:\n"
            for i, doc in enumerate(documents[:3], 1):
                prompt += f"{i}. {doc.get('document_name', 'Document')}"
                if doc.get('section_direct'):
                    prompt += f" - Section: {doc.get('section_direct')}"
                prompt += "\n"
        
        # Add conversation context
        if context:
            prompt += f"\nConversation context:\n{context}\n"
        
        prompt += "\nRespond directly to the student's question. Be helpful and clear."
        
        return prompt


def stream_response_to_sse(
    course_id: int,
    question: str,
    user=None,
    include_context: bool = True
) -> Generator[str, None, None]:
    """
    Public function to stream response as SSE.
    
    Usage in Django view:
        return StreamingHttpResponse(
            stream_response_to_sse(course_id, question, user),
            content_type='text/event-stream'
        )
    
    Args:
        course_id: Course ID
        question: User question
        user: User object
        include_context: Include conversation context
    
    Yields:
        SSE-formatted event strings
    """
    generator = StreamingAnswerGenerator()
    yield from generator.stream_question_answer(
        course_id=course_id,
        question=question,
        user=user,
        include_context=include_context
    )
