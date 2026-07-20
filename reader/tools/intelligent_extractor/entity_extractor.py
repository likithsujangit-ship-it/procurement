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
        """Loads the appropriate schema based on the intent. Fallback to generic if not found."""
        schema_path = self.schema_dir / f"{intent}_schema.json"
        if not schema_path.exists():
            logger.warning(f"Schema not found for intent '{intent}'. Falling back to generic schema approach.")
            # For unknown, we can just return a basic schema so it doesn't crash, or raise.
            # We'll just return a minimal schema
            return {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "const": intent},
                    "missing_fields": {"type": "array"}
                },
                "required": ["intent"]
            }
            
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

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
                    raise SchemaValidationError(f"Extraction failed after {self.max_retries} attempts. Last error: {e}")
                
                # Append error to prompt for next attempt
                current_prompt += f"\n\nYOUR PREVIOUS RESPONSE CAUSED THIS ERROR: {e}\nPLEASE FIX THE JSON FORMAT AND TRY AGAIN."
