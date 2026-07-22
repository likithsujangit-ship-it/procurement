import json
import logging
import re
from .prompts import CLASSIFICATION_PROMPT
from .classifier_models import ExtractedDocument
from .exceptions import SchemaValidationError
from tools.groq_client import GroqClient

logger = logging.getLogger(__name__)


class DocumentClassifier:
    def __init__(self):
        self.llm = GroqClient()

    def _classify_with_regex(self, unified_context: str) -> ExtractedDocument:
        """Rule-based regex fallback classification when LLM call fails or hits rate limits."""
        text = unified_context.lower()
        if any(w in text for w in ("request for quotation", "rfq", "quote request", "quotation")):
            intent = "request_for_quotation"
        elif any(w in text for w in ("purchase order", "po#", "po number", "po_")):
            intent = "purchase_order_issuance"
        elif any(w in text for w in ("shipment", "dispatch", "tracking", "delivery note", "bill of lading")):
            intent = "shipment_dispatch_notification"
        elif any(w in text for w in ("invoice", "tax invoice", "bill", "payment request")):
            intent = "invoice_only"
        else:
            intent = "other"
            
        logger.info(f"Regex fallback classifier assigned intent '{intent}' with confidence 0.70")
        return ExtractedDocument(file="unified_context", intent=intent, confidence=0.70)

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
            return self._classify_with_regex(unified_context)
        except Exception as e:
            logger.warning(f"LLM classification failed ({e}). Triggering rule-based regex classifier fallback...")
            return self._classify_with_regex(unified_context)
