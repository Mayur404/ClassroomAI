"""
Centralized error handling for DRF endpoints.
Provides consistent error response format across the API.
"""
import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class APIError(APIException):
    """Base class for API errors with custom response format."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "An error occurred."
    default_code = "error"
    
    def __init__(self, detail=None, code=None, correlation_id=None):
        if detail is None:
            detail = self.default_detail
        if code is None:
            code = self.default_code
        
        self.detail = detail
        self.code = code
        self.correlation_id = correlation_id
        super().__init__(detail, code)


class ValidationError(APIError):
    """400 - Request validation failed."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Validation error."
    default_code = "validation_error"


class InputSanitizationError(APIError):
    """400 - Input contains invalid or unsafe content."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Input contains invalid content."
    default_code = "input_sanitization_error"


class NotFoundError(APIError):
    """404 - Resource not found."""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Resource not found."
    default_code = "not_found"


class PermissionError(APIError):
    """403 - User lacks permission."""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Permission denied."
    default_code = "permission_denied"


class ServiceUnavailableError(APIError):
    """503 - External service unavailable."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable."
    default_code = "service_unavailable"


class OllamaConnectionError(ServiceUnavailableError):
    """503 - Cannot connect to Ollama."""
    default_detail = "LLM service unavailable. Ensure Ollama is running."
    default_code = "ollama_unavailable"


class ChromaDBError(ServiceUnavailableError):
    """503 - ChromaDB error."""
    default_detail = "Vector database error."
    default_code = "chromadb_error"


class PDFExtractionError(APIError):
    """400 - PDF extraction failed."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Failed to extract text from PDF."
    default_code = "pdf_extraction_error"


class RateLimitError(APIError):
    """429 - Rate limit exceeded."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Rate limit exceeded. Please try again later."
    default_code = "rate_limit_exceeded"


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.
    Returns consistent error response format with correlation ID.
    """
    from rest_framework.views import exception_handler
    
    request = context.get("request")
    correlation_id = getattr(request, "correlation_id", "unknown") if request else "unknown"
    
    # Let DRF handle standard API exceptions first
    response = exception_handler(exc, context)
    
    if response is not None:
        # DRF handled it (e.g. ValidationError, NotAuthenticated, etc).
        status_code = response.status_code
        
        # Extract meaningful error message
        if isinstance(response.data, dict):
            # Try to format DRF validation errors
            if "detail" in response.data:
                error_msg = response.data["detail"]
            else:
                # Combine validation errors
                error_msg = response.data
        elif isinstance(response.data, list):
            error_msg = response.data[0]
        else:
            error_msg = str(response.data)
            
        code = getattr(exc, "get_codes", lambda: "validation_error")()
        if isinstance(code, dict):
            code = "validation_error"  # fallback code 
            
    elif isinstance(exc, APIError):
        # Custom APIError fallback
        status_code = exc.status_code
        error_msg = exc.detail
        code = getattr(exc, "code", "error")
        correlation_id = exc.correlation_id or correlation_id
    elif isinstance(exc, (ValueError, TypeError)):
        status_code = status.HTTP_400_BAD_REQUEST
        error_msg = str(exc)
        code = "invalid_input"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_msg = str(exc)
        code = getattr(exc, "code", "error")
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True, extra={"correlation_id": correlation_id})
    
    # Standard error response format
    response_data = {
        "success": False,
        "error": error_msg,
        "code": code,
        "correlation_id": correlation_id,
    }
    
    return Response(response_data, status=status_code)



class ErrorResponse:
    """Utility class for building consistent error responses."""
    
    @staticmethod
    def build(error_type, message, correlation_id=None, data=None):
        """Build a structured error response."""
        response = {
            "success": False,
            "error": message,
            "code": error_type,
        }
        if correlation_id:
            response["correlation_id"] = correlation_id
        if data:
            response["data"] = data
        return response
    
    @staticmethod
    def validation(field, message, correlation_id=None):
        """Build a validation error response."""
        return ErrorResponse.build("validation_error", message, correlation_id, {"field": field})
    
    @staticmethod
    def not_found(resource_type, resource_id, correlation_id=None):
        """Build a not found error response."""
        return ErrorResponse.build(
            "not_found",
            f"{resource_type} with ID {resource_id} not found",
            correlation_id,
        )
