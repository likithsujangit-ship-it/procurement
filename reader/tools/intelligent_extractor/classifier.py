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
        # Check for hybrid first (both PO and Invoice/RFQ keywords present)
        has_po = any(w in text for w in ("purchase order", "po#", "po number", "po_"))
        has_invoice = any(w in text for w in ("invoice", "tax invoice", "bill", "payment request"))
        has_rfq = any(w in text for w in ("request for quotation", "rfq", "quote request", "quotation"))
        
        if (has_po and has_invoice) or (has_rfq and has_po) or (has_rfq and has_invoice):
            intent = "hybrid_procurement"
        elif has_rfq:
            intent = "request_for_quotation"
        elif has_po:
            intent = "purchase_order_issuance"
        elif any(w in text for w in ("shipment", "dispatch", "tracking", "delivery note", "bill of lading")):
            intent = "shipment_dispatch_notification"
        elif has_invoice:
            intent = "invoice_only"
        else:
            intent = "other"
            
        logger.info(f"Regex fallback classifier assigned intent '{intent}' with confidence 0.70")
        return ExtractedDocument(file="unified_context", intent=intent, confidence=0.70)

    def classify(self, unified_context: str) -> ExtractedDocument:
        """Classifies the main document based on unified context."""
        prompt = CLASSIFICATION_PROMPT.format(context=unified_context)
        
        # Try models in order: 70b first, then 8b fallback
        for model in ["nousresearch/hermes-3-llama-3.1-405b", "meta-llama/llama-3.3-70b-instruct"]:
            try:
                # Truncate context for 8b model to fit within TPM limits
                model_prompt = prompt
                if "8b" in model.lower() and len(unified_context) > 4000:
                    truncated_ctx = unified_context[:4000]
                    model_prompt = CLASSIFICATION_PROMPT.format(context=truncated_ctx)

                response_text = self.llm.get_completion(
                    system_prompt="You are an expert document classifier. Return ONLY valid JSON.",
                    user_prompt=model_prompt,
                    model=model,
                    response_json=True,
                    task="classification"
                )
                data = json.loads(response_text)
                return ExtractedDocument(**data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse classification JSON from model '{model}': {e}")
                continue
            except Exception as e:
                logger.warning(f"LLM classification failed for model '{model}' ({e}).")
                continue
        
        logger.warning("All LLM classification models failed. Triggering rule-based regex classifier fallback...")
        return self._classify_with_regex(unified_context)
