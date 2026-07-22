"""
Unit Tests for Date Abbreviation ("Dt.") and Date Extension Recognition.
Verifies regex hint pass and LLM prompt hints for dates like "Dt.31-05-2025" and "extended up to 30-06-2025".
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from tools.intelligent_extractor.entity_extractor import extract_date_hints, EntityExtractor
from tools.intelligent_extractor.orchestrator import run_pre_extraction_pass


def test_extract_date_hints_regex():
    """Verify regex patterns capture Dt.31-05-2025 and extended due date 30-06-2025."""
    sample_text = (
        "This office Enq. No.: M100028013 -M09/2025-26, Dt. 31-05-2025.\n"
        "Above enquiry was issued under E-Procurement system for supply of C-JET Fire Fighting Hose pipe "
        "with due date on 19-06-2025. Further, due date is extended up to 30-06-2025."
    )

    hints = extract_date_hints(sample_text)

    # Check dated abbreviation matches
    assert "dated_abbreviation_matches (Dt. -> rfq_issue_date candidate)" in hints
    assert "31-05-2025" in hints["dated_abbreviation_matches (Dt. -> rfq_issue_date candidate)"]

    # Check extended due date matches
    assert "extended_due_date_matches (authoritative quotation_due_date candidate)" in hints
    assert "30-06-2025" in hints["extended_due_date_matches (authoritative quotation_due_date candidate)"]

    # Check original due date matches
    assert "original_due_date_matches (date_extended_from candidate)" in hints
    assert "19-06-2025" in hints["original_due_date_matches (date_extended_from candidate)"]


def test_run_pre_extraction_pass_incorporates_date_candidates():
    """Verify orchestrator run_pre_extraction_pass includes targeted date hints."""
    sample_text = "Enquiry No. M100028013, Dt.31-05-2025. due date on 19-06-2025 extended up to 30-06-2025."
    hints = run_pre_extraction_pass(sample_text)

    assert "dated_abbreviation_matches (Dt. -> issue date candidate)" in hints
    assert "31-05-2025" in hints["dated_abbreviation_matches (Dt. -> issue date candidate)"]
    assert "extended_due_date_matches (authoritative quotation_due_date candidate)" in hints
    assert "30-06-2025" in hints["extended_due_date_matches (authoritative quotation_due_date candidate)"]


@patch("tools.intelligent_extractor.entity_extractor.GroqClient")
def test_mock_date_extraction_assignment(mock_groq):
    """Mock LLM response to confirm rfq_issue_date and quotation_due_date are correctly populated."""
    extractor = EntityExtractor()

    expected_json = json.dumps({
        "intent": "request_for_quotation",
        "document_type": ["RFQ"],
        "buyer": {"company_name": "APGENCO", "contact_name": "VeeraSekhar ADE", "email": "rtpp.purchase@apgenco.gov.in"},
        "supplier": {"company_name": "Jyothi Rubber Udyog", "contact_name": "Jyoti", "email": "jyoti@jyotirubber.com"},
        "rfq_number": "M100028013",
        "rfq_issue_date": "2025-05-31",
        "quotation_due_date": "2025-06-30",
        "date_extended_from": "2025-06-19",
        "items": [
            {
                "line": 1,
                "part_number": "200017447",
                "description": "C-JET Fire Hose",
                "quantity": 50,
                "unit": "NO"
            }
        ],
        "attachments": []
    })

    mock_instance = mock_groq.return_value
    mock_instance.get_chat_completion.return_value = expected_json

    doc_text = "Enquiry No. M100028013, Dt. 31-05-2025. due date on 19-06-2025 extended up to 30-06-2025."
    result = extractor.extract(doc_text, "request_for_quotation")

    assert result["extraction_status"] == "success"
    assert result["rfq_issue_date"] == "2025-05-31"
    assert result["quotation_due_date"] == "2025-06-30"
    assert result.get("date_extended_from") == "2025-06-19"
