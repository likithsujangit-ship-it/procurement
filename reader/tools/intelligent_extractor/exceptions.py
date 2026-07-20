class IntelligentExtractionError(Exception):
    """Base exception for intelligent extractor."""
    pass

class SchemaValidationError(IntelligentExtractionError):
    """Raised when LLM output fails Pydantic schema validation."""
    pass

class ContextTooLargeError(IntelligentExtractionError):
    """Raised when unified context exceeds LLM token limits."""
    pass
