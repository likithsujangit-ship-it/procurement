import json
import logging
from .prompts import CLASSIFICATION_PROMPT
from .classifier_models import ExtractedDocument
from .exceptions import SchemaValidationError
from tools.groq_client import GroqClient

logger = logging.getLogger(__name__)

class DocumentClassifier:
    def __init__(self):
        self.llm = GroqClient()

    def classify(self, unified_context: str) -> ExtractedDocument:
        """Classifies the main document based on unified context."""
        prompt = CLASSIFICATION_PROMPT.format(context=unified_context)
        
        try:
            response_text = self.llm.get_completion(
                system_prompt="You are an expert document classifier. Return ONLY valid JSON.",
                user_prompt=prompt,
                response_json=True
            )
            data = json.loads(response_text)
            return ExtractedDocument(**data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse classification JSON: {e}")
            raise SchemaValidationError(f"Invalid JSON returned by LLM: {response_text}")
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise
