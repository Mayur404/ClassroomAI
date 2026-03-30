"""
Server-Sent Events (SSE) streaming for real-time answer generation.
Shows user: retrieving → searching → generating → complete states.
"""
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
import json
import logging
import time
from typing import Generator, Dict, Any
import uuid

logger = logging.getLogger(__name__)


class StreamingGenerator:
    """Manages streaming events to client."""
    
    def __init__(self, correlation_id: str = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.event_id = 0
    
    def send_event(self, event_type: str, data: Dict[str, Any], retry: int = None) -> str:
        """
        Format and return SSE event.
        
        Args:
            event_type: Type of event (retrieving, searching, generating, complete, error)
            data: Event data
            retry: Milliseconds before client auto-reconnects
        
        Returns:
            SSE formatted event string
        """
        self.event_id += 1
        
        event = f"id: {self.event_id}\n"
        event += f"event: {event_type}\n"
        
        # Add retry if specified
        if retry:
            event += f"retry: {retry}\n"
        
        # Add data with proper escaping
        data_str = json.dumps({
            "timestamp": time.time(),
            "correlation_id": self.correlation_id,
            **data
        })
        
        # Split data across multiple lines if needed
        for line in data_str.split('\n'):
            event += f"data: {line}\n"
        
        event += "\n"  # Double newline to end event
        
        logger.debug(f"SSE Event {self.event_id}: {event_type}")
        
        return event


def stream_chat_response(query: str, 
                         chat_service,
                         user_id: int = None) -> Generator[str, None, None]:
    """
    Stream chat response with multiple progress states.
    
    Yields SSE events showing:
    1. Retrieving documents
    2. Searching knowledge base
    3. Generating answer
    4. Complete
    5. Possible errors
    """
    generator = StreamingGenerator()
    
    try:
        # Event 1: Start
        yield generator.send_event("start", {
            "status": "initialized",
            "message": "Processing your question..."
        })
        
        # Event 2: Retrieving documents
        yield generator.send_event("retrieving", {
            "status": "retrieving",
            "message": "Searching course materials...",
            "progress": 10
        }, retry=30000)
        
        # Retrieve documents
        start = time.time()
        try:
            documents = chat_service.retrieve_documents(query, top_k=5)
            retrieval_time = (time.time() - start) * 1000
            
            yield generator.send_event("retrieved", {
                "status": "retrieved",
                "message": f"Found {len(documents)} relevant materials",
                "progress": 30,
                "documents_count": len(documents),
                "retrieval_time_ms": retrieval_time,
                "documents": [
                    {
                        "id": d.get("id"),
                        "title": d.get("title", "Unknown"),
                        "relevance_score": d.get("score", 0),
                    }
                    for d in documents[:3]  # Send top 3 docs
                ]
            })
        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            yield generator.send_event("error", {
                "status": "retrieval_failed",
                "message": "Could not retrieve documents",
                "error": str(e),
                "code": "RETRIEVAL_ERROR"
            })
            return
        
        # Event 3: Generating answer
        yield generator.send_event("generating", {
            "status": "generating",
            "message": "Generating answer...",
            "progress": 50
        }, retry=30000)
        
        # Generate answer with streaming
        start = time.time()
        answer_chunks = []
        
        try:
            for chunk in chat_service.generate_answer_streaming(
                query=query,
                documents=documents,
                user_id=user_id
            ):
                answer_chunks.append(chunk)
                
                # Send incremental answer
                yield generator.send_event("answer_chunk", {
                    "status": "streaming_answer",
                    "chunk": chunk,
                    "progress": 50 + min(40, len(answer_chunks) * 5)  # Progress up to 90%
                })
                
                # Small delay to avoid overwhelming client
                time.sleep(0.01)
            
            generation_time = (time.time() - start) * 1000
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            yield generator.send_event("error", {
                "status": "generation_failed",
                "message": "Failed to generate answer",
                "error": str(e),
                "code": "GENERATION_ERROR"
            })
            return
        
        # Event 4: Complete
        full_answer = "".join(answer_chunks)
        
        yield generator.send_event("complete", {
            "status": "complete",
            "message": "Answer complete",
            "progress": 100,
            "answer": full_answer,
            "generation_time_ms": generation_time,
            "total_documents": len(documents),
            "quality_score": chat_service.calculate_answer_quality(full_answer, documents)
        })
    
    except Exception as e:
        logger.error(f"Stream generation failed: {e}", exc_info=True)
        yield generator.send_event("error", {
            "status": "failed",
            "message": "An unexpected error occurred",
            "error": str(e),
            "code": "INTERNAL_ERROR"
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_answer(request):
    """
    SSE endpoint for streaming answers.
    
    POST /api/chat/stream-answer/
    {
        "query": "What is photosynthesis?",
        "course_id": 1
    }
    
    Response: Server-Sent Events stream
    """
    try:
        query = request.data.get("query", "").strip()
        course_id = request.data.get("course_id")
        
        if not query:
            return StreamingHttpResponse(
                [json.dumps({"error": "Query required"})],
                content_type="application/json",
                status=400
            )
        
        # Get chat service
        from apps.chat.services import ChatService
        chat_service = ChatService(course_id=course_id, user=request.user)
        
        # Create response with SSE content type
        response = StreamingHttpResponse(
            stream_chat_response(query, chat_service, request.user.id),
            content_type="text/event-stream"
        )
        
        # Required headers for SSE
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        
        return response
    
    except Exception as e:
        logger.error(f"Stream endpoint error: {e}", exc_info=True)
        return StreamingHttpResponse(
            [json.dumps({"error": str(e)})],
            content_type="application/json",
            status=500
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_assignment_generation(request):
    """
    SSE endpoint for streaming assignment generation.
    
    Shows progress: planning → generating questions → complete
    """
    generator = StreamingGenerator()
    
    def generation_stream():
        try:
            course_id = request.data.get("course_id")
            num_questions = request.data.get("num_questions", 5)
            
            yield generator.send_event("start", {
                "status": "started",
                "message": "Starting assignment generation..."
            })
            
            # Step 1: Planning
            yield generator.send_event("planning", {
                "status": "planning",
                "message": "Analyzing course materials...",
                "progress": 20
            })
            
            time.sleep(0.5)  # Simulate work
            
            # Step 2: Generating questions
            from apps.ai_service.answer_generator import AssignmentGenerator
            generator_service = AssignmentGenerator()
            
            questions = []
            for i in range(num_questions):
                yield generator.send_event("generating_question", {
                    "status": "generating",
                    "message": f"Generating question {i+1}/{num_questions}",
                    "progress": 20 + (i + 1) * (60 // num_questions),
                    "current_question": i + 1,
                    "total_questions": num_questions
                })
                
                # Generate single question
                q = generator_service.generate_single_question(course_id)
                questions.append(q)
                time.sleep(0.1)
            
            # Step 3: Complete
            yield generator.send_event("complete", {
                "status": "complete",
                "message": "Assignment generated successfully",
                "progress": 100,
                "questions": questions,
                "count": len(questions)
            })
        
        except Exception as e:
            logger.error(f"Assignment generation stream error: {e}")
            yield generator.send_event("error", {
                "status": "error",
                "message": str(e),
                "code": "GENERATION_FAILED"
            })
    
    response = StreamingHttpResponse(
        generation_stream(),
        content_type="text/event-stream"
    )
    
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_pdf_extraction(request):
    """
    SSE endpoint for streaming PDF extraction progress.
    
    Shows: starting → extracting → quality_check → complete
    """
    generator = StreamingGenerator()
    
    def extraction_stream():
        try:
            material_id = request.data.get("material_id")
            
            from apps.courses.models import CourseMaterial
            material = CourseMaterial.objects.get(id=material_id)
            
            yield generator.send_event("start", {
                "status": "started",
                "message": f"Extracting {material.file.name}...",
                "file_name": material.file.name
            })
            
            # Queue async extraction
            from apps.celery_tasks import extract_pdf_async
            task = extract_pdf_async.delay(material_id, str(material.file.path))
            
            # Poll task status
            import time
            start_time = time.time()
            while time.time() - start_time < 300:  # 5 minute timeout
                from celery.result import AsyncResult
                result = AsyncResult(task.id)
                
                if result.status == "PENDING":
                    yield generator.send_event("extracting", {
                        "status": "extracting",
                        "message": "Extracting text from PDF...",
                        "progress": 50,
                        "task_id": task.id
                    })
                
                elif result.status == "PROGRESS":
                    progress = result.info.get("current", 50)
                    yield generator.send_event("progress", {
                        "status": "extracting",
                        "message": f"Processing page {result.info.get('current')}/{result.info.get('total')}",
                        "progress": progress,
                        "task_id": task.id
                    })
                
                elif result.status == "SUCCESS":
                    material.refresh_from_db()
                    yield generator.send_event("complete", {
                        "status": "complete",
                        "message": "Extraction complete",
                        "progress": 100,
                        "pages": material.pages,
                        "quality_score": material.extraction_quality_score,
                        "method": material.extraction_method
                    })
                    break
                
                elif result.status == "FAILURE":
                    raise Exception(f"Extraction failed: {result.info}")
                
                time.sleep(1)
            
            else:
                raise Exception("Extraction timeout")
        
        except Exception as e:
            logger.error(f"PDF extraction stream error: {e}")
            yield generator.send_event("error", {
                "status": "error",
                "message": str(e),
                "code": "EXTRACTION_FAILED"
            })
    
    response = StreamingHttpResponse(
        extraction_stream(),
        content_type="text/event-stream"
    )
    
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    
    return response


# ============================================================================
# CLIENT-SIDE JAVASCRIPT FOR SSE 
# ============================================================================

SSE_CLIENT_CODE = """
// Frontend SSE client for connecting to streaming endpoints

class StreamingClient {
    constructor(url, onEvent, onError) {
        this.url = url;
        this.onEvent = onEvent;
        this.onError = onError;
        this.eventSource = null;
    }
    
    connect(data = {}) {
        // Since EventSource doesn't support POST, we'll use fetch with streaming
        this.stream(data);
    }
    
    async stream(data = {}) {
        try {
            const response = await fetch(this.url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify(data)
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                // Process complete events
                const parts = buffer.split('\\n\\n');
                buffer = parts[parts.length - 1];
                
                for (let i = 0; i < parts.length - 1; i++) {
                    this.parseEvent(parts[i]);
                }
            }
        } catch (error) {
            this.onError(error);
        }
    }
    
    parseEvent(eventString) {
        const lines = eventString.trim().split('\\n');
        const event = {};
        
        for (const line of lines) {
            if (line.startsWith('event:')) {
                event.type = line.substring(6).trim();
            } else if (line.startsWith('data:')) {
                if (!event.data) event.data = '';
                event.data += line.substring(5).trim();
            } else if (line.startsWith('id:')) {
                event.id = line.substring(3).trim();
            }
        }
        
        if (event.data) {
            try {
                event.data = JSON.parse(event.data);
            } catch (e) {
                // Keep as string
            }
        }
        
        this.onEvent(event);
    }
    
    getToken() {
        // Get JWT token from localStorage or elsewhere
        return localStorage.getItem('token');
    }
    
    close() {
        if (this.eventSource) {
            this.eventSource.close();
        }
    }
}

// Usage Example:
/*
const client = new StreamingClient(
    '/api/chat/stream-answer/',
    (event) => {
        console.log('Event:', event.type, event.data);
        if (event.type === 'complete') {
            console.log('Answer:', event.data.answer);
        }
    },
    (error) => console.error('Error:', error)
);

client.connect({ query: 'What is AI?', course_id: 1 });
*/
"""
