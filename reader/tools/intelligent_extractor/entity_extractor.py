import json
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from tools.utils import setup_logger
from tools.groq_client import GroqClient
from .prompts import EXTRACTION_PROMPT, SYSTEM_PROMPT
from .validate_extraction import validate_extraction

logger = setup_logger("entity_extractor")


import re

def extract_date_hints(text: str) -> Dict[str, Any]:
    """Helper to detect date abbreviations and due date extensions from text."""
    dt_dates = sorted(list(set(re.findall(r'(?:Dt|Dtd|Dated)\.?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE))))
    extended_due_dates = sorted(list(set(re.findall(r'due\s+date.*?(?:extended\s+up\s+to|extended\s+to)\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE | re.DOTALL))))
    original_due_dates = sorted(list(set(re.findall(r'due\s+date\s+(?:on|is)?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})', text, re.IGNORECASE))))
    
    hints = {}
    if dt_dates:
        hints["dated_abbreviation_matches (Dt. -> rfq_issue_date candidate)"] = dt_dates
    if extended_due_dates:
        hints["extended_due_date_matches (authoritative quotation_due_date candidate)"] = extended_due_dates
    if original_due_dates:
        hints["original_due_date_matches (date_extended_from candidate)"] = original_due_dates
    return hints


class EntityExtractor:
    def __init__(self, max_repairs_per_model: int = 2):
        self.llm = GroqClient()
        self.max_repairs_per_model = max_repairs_per_model
        self.schema_dir = Path(__file__).resolve().parent.parent.parent / "schemas"
        self.fallback_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-70b-8192"
        ]

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

    def _validate_raw_response(self, response_text: str, expected_intent: str) -> Tuple[bool, Optional[dict], str, str]:
        """
        Attempts to json.loads() response_text and validates against validate_extraction.py.
        Returns: (is_valid, parsed_data_dict, error_type, specific_error_message)
        """
        try:
            data = json.loads(response_text)
        except Exception as json_err:
            return False, None, "JSONDecodeError", f"JSON parsing failed: {json_err}"

        if not isinstance(data, dict):
            return False, None, "JSONDecodeError", "Output is not a valid JSON object."

        if "intent" not in data or not data["intent"]:
            data["intent"] = expected_intent

        is_valid, errors, warnings, schema_used = validate_extraction(data)
        if not is_valid:
            err_msg = f"Schema validation failed against {schema_used}: " + "; ".join(errors)
            return False, data, "SchemaValidationError", err_msg

        return True, data, "", ""

    def extract(self, unified_context: str, intent: str, hints: Optional[Dict[str, Any]] = None) -> dict:
        """
        Extracts structured entities from unified context.
        State Machine: PENDING -> EXTRACTING -> SUCCESS or FAILED.
        Only SUCCESS state is allowed to populate buyer/supplier/items/confidence.
        """
        active_hints = dict(hints or {})
        active_hints.update(extract_date_hints(unified_context))

        schema_dict = self._load_schema_for_intent(intent)
        schema_str = json.dumps(schema_dict, indent=2)
        hints_str = json.dumps(active_hints, indent=2)
        
        initial_prompt = EXTRACTION_PROMPT.format(context=unified_context, schema=schema_str, hints=hints_str)

        # Clear per-run state variables completely
        last_raw_output = ""
        last_error_type = ""
        last_error_details = ""
        primary_model = self.fallback_models[0]

        for model in self.fallback_models:
            logger.info(f"Initiating entity extraction with model '{model}'...")
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": initial_prompt}
            ]

            repair_attempt = 0

            while repair_attempt <= self.max_repairs_per_model:
                try:
                    if repair_attempt > 0:
                        logger.warning(
                            f"Repair attempt {repair_attempt}/{self.max_repairs_per_model} for model '{model}' "
                            f"due to {last_error_type}: {last_error_details}"
                        )

                    response_text = self.llm.get_chat_completion(
                        messages=messages,
                        model=model,
                        response_json=True,
                        json_schema=schema_dict
                    )

                    last_raw_output = response_text
                    
                    is_valid, data, err_type, err_details = self._validate_raw_response(response_text, intent)
                    if is_valid and data is not None:
                        if repair_attempt > 0:
                            logger.info(f"Model '{model}' successfully repaired JSON on attempt {repair_attempt}!")
                        
                        data["extraction_status"] = "success"
                        data["extraction_failed"] = False
                        data["failure_reason"] = None
                        data["extracted_with_model"] = model
                        data["extracted_with_fallback_model"] = (model != primary_model)
                        return data

                    last_error_type = err_type
                    last_error_details = err_details

                except Exception as api_err:
                    last_error_type = "APIError"
                    last_error_details = str(api_err)
                    logger.warning(f"API call failed for model '{model}' on attempt {repair_attempt}: {api_err}")
                    # Quota exhausted — no point retrying any model or repair attempt
                    if "Preflight token quota check failed" in last_error_details:
                        break

                if repair_attempt < self.max_repairs_per_model:
                    repair_attempt += 1
                    correction_prompt = (
                        f"The previous response contained {last_error_type} errors:\n"
                        f"{last_error_details}\n\n"
                        f"MALFORMED OUTPUT:\n{last_raw_output}\n\n"
                        f"Please correct all errors and return ONLY a valid raw JSON object matching the required schema. "
                        f"Do not include code blocks, markdown formatting, or explanations."
                    )
                    messages.append({"role": "assistant", "content": last_raw_output})
                    messages.append({"role": "user", "content": correction_prompt})
                else:
                    logger.warning(
                        f"Max repair attempts ({self.max_repairs_per_model}) reached for model '{model}'. "
                        f"Falling back to next model if available."
                    )
                    break

            # Propagate quota failure immediately — all models share the same daily limit
            if "Preflight token quota check failed" in last_error_details:
                break

        fail_msg = f"API error across all models: {last_error_details}" if last_error_details else "All model extraction attempts failed"
        logger.error(
            "All model extraction attempts and repair retries failed. "
            f"Returning extraction_status=failed with null fields ({fail_msg})."
        )
        return {
            "extraction_status": "failed",
            "extraction_failed": True,
            "failure_reason": fail_msg,
            "extracted_with_model": None,
            "raw_output": last_raw_output,
            "error_type": last_error_type,
            "error": last_error_details,
            "intent": intent,
            "document_type": None,
            "buyer": None,
            "supplier": None,
            "items": None,
            "commercial_terms": None,
            "delivery_requirements": None,
            "shipping_details": None,
            "approval": None,
            "attachments": [],
            "missing_fields": [],
            "conflicts": [],
            "llm_confidence_score": None,
            "calculated_confidence_score": None,
            "confidence_discrepancy_flag": False,
            "extracted_with_fallback_model": False
        }

