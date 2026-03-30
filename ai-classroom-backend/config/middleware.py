"""
Custom middleware for logging, error handling, and request tracking.
"""
import uuid
import logging
import json
import time
from django.http import JsonResponse
from django.utils.decorators import sync_and_async_middleware

logger = logging.getLogger(__name__)


@sync_and_async_middleware
def RequestLoggingMiddleware(get_response):
    """
    Logs all requests with correlation IDs for debugging and tracing.
    Measures request duration and logs performance metrics.
    """
    def middleware(request):
        # Generate unique correlation ID for request tracing
        correlation_id = str(uuid.uuid4())
        request.correlation_id = correlation_id
        
        # Add to request headers
        request.META["HTTP_X_CORRELATION_ID"] = correlation_id
        
        start_time = time.time()
        
        # Log incoming request
        logger.info(
            f"Incoming request: {request.method} {request.path}",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.path,
                "user_id": request.user.id if request.user.is_authenticated else "anonymous",
            }
        )
        
        response = get_response(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log outgoing response
        logger.info(
            f"Request completed: {request.method} {request.path} -> {response.status_code}",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            }
        )
        
        # Add correlation ID to response
        response["X-Correlation-ID"] = correlation_id
        
        return response
    
    return middleware


@sync_and_async_middleware
def ErrorHandlingMiddleware(get_response):
    """
    Catches unhandled exceptions and returns structured error responses.
    """
    def middleware(request):
        try:
            response = get_response(request)
        except Exception as e:
            correlation_id = getattr(request, "correlation_id", str(uuid.uuid4()))
            
            logger.error(
                f"Unhandled exception in {request.method} {request.path}: {str(e)}",
                extra={
                    "correlation_id": correlation_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            
            response = JsonResponse(
                {
                    "success": False,
                    "error": "Internal server error",
                    "correlation_id": correlation_id,
                    "details": str(e) if getattr(request, "debug", False) else None,
                },
                status=500,
            )
            response["X-Correlation-ID"] = correlation_id
        
        return response
    
    return middleware
