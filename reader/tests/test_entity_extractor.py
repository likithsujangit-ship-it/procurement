import pytest
import json
from unittest.mock import MagicMock, patch
from tools.intelligent_extractor.entity_extractor import EntityExtractor

def test_validate_raw_response_invalid_json():
    extractor = EntityExtractor()
    is_valid, data, err_type, err_msg = extractor._validate_raw_response("Not a JSON string", "request_for_quotation")
    assert is_valid is False
    assert data is None
    assert err_type == "JSONDecodeError"
    assert "JSON parsing failed" in err_msg

def test_validate_raw_response_schema_non_conformance():
    extractor = EntityExtractor()
    # Invalid quantity type (string instead of int/number)
    bad_json = json.dumps({
        "intent": "request_for_quotation",
        "document_type": ["RFQ"],
        "buyer": {"company_name": "Acme", "contact_name": "John", "email": "j@a.com"},
        "supplier": {"company_name": "Sup", "contact_name": "Jane", "email": "j@s.com"},
        "items": [{"part_number": "P1", "description": "Desc", "quantity": "ten", "unit": "pcs"}],
        "attachments": []
    })
    is_valid, data, err_type, err_msg = extractor._validate_raw_response(bad_json, "request_for_quotation")
    assert is_valid is False
    assert err_type == "SchemaValidationError"
    assert "quantity" in err_msg.lower()

@patch("tools.intelligent_extractor.entity_extractor.GroqClient")
def test_repair_attempt_success(mock_groq):
    extractor = EntityExtractor(max_repairs_per_model=2)
    
    valid_payload = json.dumps({
        "intent": "request_for_quotation",
        "document_type": ["RFQ"],
        "buyer": {"company_name": "Acme", "contact_name": "John", "email": "j@a.com"},
        "supplier": {"company_name": "Sup", "contact_name": "Jane", "email": "j@s.com"},
        "items": [{"part_number": "P1", "description": "Desc", "quantity": 10, "unit": "pcs"}],
        "attachments": []
    })
    
    # 1st call returns malformed JSON, 2nd call (repair attempt 1) returns valid payload
    extractor.llm.get_chat_completion = MagicMock(side_effect=[
        "INVALID JSON {{{",
        valid_payload
    ])
    
    res = extractor.extract("some context", "request_for_quotation")
    assert res.get("intent") == "request_for_quotation"
    assert res.get("extraction_failed") is not True
    assert res.get("extracted_with_model") == "llama-3.3-70b-versatile"
    assert extractor.llm.get_chat_completion.call_count == 2

@patch("tools.intelligent_extractor.entity_extractor.GroqClient")
def test_all_attempts_fail_returns_partial_extraction(mock_groq):
    extractor = EntityExtractor(max_repairs_per_model=2)
    
    # Return malformed output continuously
    extractor.llm.get_chat_completion = MagicMock(return_value="MALFORMED_OUTPUT")
    
    res = extractor.extract("some context", "request_for_quotation")
    assert res.get("extraction_failed") is True
    assert res.get("extracted_with_model") is None
    assert res.get("raw_output") == "MALFORMED_OUTPUT"
    assert res.get("error_type") == "JSONDecodeError"

