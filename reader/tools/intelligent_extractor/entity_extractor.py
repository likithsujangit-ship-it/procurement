import json
import logging
from pathlib import Path
from .prompts import EXTRACTION_PROMPT, SYSTEM_PROMPT
from .exceptions import SchemaValidationError
from tools.groq_client import GroqClient

logger = logging.getLogger(__name__)

class EntityExtractor:
    def __init__(self, max_retries: int = 3):
        self.llm = GroqClient()
        self.max_retries = max_retries
        self.schema_dir = Path(__file__).resolve().parent.parent.parent / "schemas"

    def _load_schema_for_intent(self, intent: str) -> dict:
        """Loads the appropriate schema based on the intent, defaulting to master procurement schema."""
        schema_path = self.schema_dir / f"{intent}_schema.json"
        master_path = self.schema_dir / "master_procurement_schema.json"
        
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif master_path.exists():
            with open(master_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            logger.warning(f"Schema not found for intent '{intent}'. Falling back to generic schema approach.")
            return {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "const": intent},
                    "missing_fields": {"type": "array"}
                },
                "required": ["intent"]
            }

    def extract(self, unified_context: str, intent: str) -> dict:
        """Extracts structured entities from unified context."""
        schema_dict = self._load_schema_for_intent(intent)
        schema_str = json.dumps(schema_dict, indent=2)
        prompt = EXTRACTION_PROMPT.format(context=unified_context, schema=schema_str)
        
        attempt = 0
        current_prompt = prompt
        
        while attempt < self.max_retries:
            try:
                response_text = self.llm.get_completion(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=current_prompt,
                    response_json=True
                )
                data = json.loads(response_text)
                return data
            except Exception as e:
                logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")
                attempt += 1
                if attempt >= self.max_retries:
                    logger.error(f"Extraction failed after {self.max_retries} attempts: {e}. Returning fallback structured dictionary.")
                    return {
                        "intent": intent,
                        "document_type": [intent.replace("_issuance", "").replace("_only", "").upper()],
                        "buyer": {"company_name": "Unknown Buyer", "contact_name": "Unknown Contact"},
                        "supplier": {"company_name": "Unknown Supplier", "contact_name": "Unknown Contact"},
                        "rfq_number": None,
                        "po_number": None,
                        "invoice_number": None,
                        "shipment_id": None,
                        "items": [],
                        "commercial_terms": {},
                        "delivery_requirements": {},
                        "shipping_details": {},
                        "approval": {},
                        "attachments": [],
                        "missing_fields": ["extracted_data_unreachable_due_to_llm_rate_limit"],
                        "conflicts": [],
                        "confidence_score": 0.3
                    }
                
                import time
                time.sleep(3)
                # Only append error if it was a JSON decoding issue, not a network/rate limit error
                if "json" in str(e).lower() or "decode" in str(e).lower():
                    current_prompt = prompt + f"\n\nPLEASE FIX JSON DECODING ERROR: {e}"
                else:
                    current_prompt = prompt
