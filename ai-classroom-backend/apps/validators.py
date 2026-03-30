"""
Input validation and sanitization utilities for the AI Classroom.
Prevents XSS, injection attacks, and validates input lengths/formats.
"""
import re
import bleach
from typing import Optional
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from django.utils.text import slugify

# ============================================================================
# SAFE HTML TAGS AND ATTRIBUTES
# ============================================================================

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "a", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td", "img", "hr"
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
}


# ============================================================================
# SANITIZATION FUNCTIONS
# ============================================================================

def sanitize_html(html_content: str, max_length: int = 10000) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.
    Removes dangerous tags and attributes.
    
    Args:
        html_content: Raw HTML string
        max_length: Maximum allowed length
        
    Returns:
        Sanitized HTML string
        
    Raises:
        ValidationError: If content exceeds max_length
    """
    if not html_content:
        return ""
    
    if len(html_content) > max_length:
        raise ValidationError(f"Content exceeds maximum length of {max_length} characters")
    
    # Use bleach to sanitize HTML
    clean = bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )
    
    return clean


def sanitize_text(text: str, max_length: int = 2000) -> str:
    """
    Sanitize plain text content.
    Removes dangerous characters and enforces length limits.
    
    Args:
        text: Raw text string
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text string
        
    Raises:
        ValidationError: If content exceeds max_length
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    if len(text) > max_length:
        raise ValidationError(f"Text exceeds maximum length of {max_length} characters")
    
    # Remove null bytes and other dangerous characters
    text = text.replace("\x00", "").replace("\r", "\n")
    
    return text


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        Safe filename
        
    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")
    
    # Block directory traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValidationError("Invalid filename: path traversal detected")
    
    # Convert to slug-like format
    name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
    safe_name = slugify(name, allow_unicode=True)
    
    if not safe_name:
        raise ValidationError("Filename contains no valid characters")
    
    # Limit length
    max_name_length = 50
    if len(safe_name) > max_name_length:
        safe_name = safe_name[:max_name_length]
    
    safe_filename = f"{safe_name}.{ext}" if ext else safe_name
    return safe_filename


def sanitize_email(email: str) -> str:
    """
    Sanitize and validate email address.
    
    Args:
        email: Email string
        
    Returns:
        Sanitized email
        
    Raises:
        ValidationError: If email is invalid
    """
    email = email.strip().lower()
    
    # Basic email validation regex
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_regex, email):
        raise ValidationError("Invalid email format")
    
    if len(email) > 254:  # RFC 5321
        raise ValidationError("Email address too long")
    
    return email


def sanitize_url(url: str) -> str:
    """
    Sanitize URL to prevent open redirect attacks.
    
    Args:
        url: URL string
        
    Returns:
        Sanitized URL (relative URL returned as-is, absolute URLs validated)
        
    Raises:
        ValidationError: If URL is malicious
    """
    if not url:
        return ""
    
    # Allow relative URLs
    if url.startswith("/") or url.startswith("#"):
        return url
    
    # Validate absolute URLs
    try:
        parsed = urlparse(url)
        
        # Only allow http and https
        if parsed.scheme not in ("http", "https", ""):
            raise ValidationError(f"Invalid URL scheme: {parsed.scheme}")
        
        # Check for javascript: and other dangerous schemes
        if url.lower().startswith(("javascript:", "data:", "vbscript:", "file:")):
            raise ValidationError("URL contains dangerous scheme")
        
        return url
    except Exception as e:
        raise ValidationError(f"Invalid URL: {str(e)}")


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_pdf_file(file_obj, max_size_mb: int = 50) -> bool:
    """
    Validate PDF file before processing.
    
    Args:
        file_obj: Django file object
        max_size_mb: Maximum file size in MB
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If file is invalid
    """
    if not file_obj:
        raise ValidationError("File is required")
    
    # Check extension
    if not file_obj.name.lower().endswith(".pdf"):
        raise ValidationError("Only PDF files are allowed")
    
    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_obj.size > max_size_bytes:
        raise ValidationError(f"File size exceeds {max_size_mb}MB limit")
    
    # Check file signature (PDF magic number)
    file_obj.seek(0)
    header = file_obj.read(4)
    file_obj.seek(0)
    
    if header != b"%PDF":
        raise ValidationError("Invalid PDF file: incorrect file signature")
    
    return True


def validate_assignment_title(title: str) -> bool:
    """Validate assignment title."""
    title = sanitize_text(title, max_length=200)
    
    if len(title) < 3:
        raise ValidationError("Title must be at least 3 characters")
    
    return True


def validate_message_content(message: str) -> str:
    """
    Validate and sanitize chat message.
    
    Args:
        message: Raw message text
        
    Returns:
        Sanitized message
    """
    message = sanitize_text(message, max_length=5000)
    
    if len(message.strip()) == 0:
        raise ValidationError("Message cannot be empty")
    
    return message


def validate_course_title(title: str) -> bool:
    """Validate course title."""
    title = sanitize_text(title, max_length=200)
    
    if len(title) < 3:
        raise ValidationError("Course title must be at least 3 characters")
    
    return True


# ============================================================================
# MODEL FIELD VALIDATORS
# ============================================================================

class MaxLengthValidator:
    """Validates maximum length with sanitization."""
    
    def __init__(self, max_length: int = 2000, sanitize: bool = True):
        self.max_length = max_length
        self.sanitize = sanitize
    
    def __call__(self, value):
        if self.sanitize:
            value = sanitize_text(value, max_length=self.max_length)
        elif len(value) > self.max_length:
            raise ValidationError(f"Text exceeds maximum length of {self.max_length}")


class HTMLSanitizerValidator:
    """Sanitizes and validates HTML content."""
    
    def __init__(self, max_length: int = 5000):
        self.max_length = max_length
    
    def __call__(self, value):
        sanitize_html(value, max_length=self.max_length)
