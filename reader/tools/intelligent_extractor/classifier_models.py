from pydantic import BaseModel

class ExtractedDocument(BaseModel):
    file: str = ""
    intent: str = "unknown"
    confidence: float = 0.0
