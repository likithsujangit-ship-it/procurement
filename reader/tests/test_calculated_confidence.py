"""Tests for objective, verified extraction-confidence signals."""

from copy import deepcopy

from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness


def _complete_rfq_payload():
    return {
        "intent": "request_for_quotation",
        "document_type": ["RFQ"],
        "llm_confidence_score": 0.95,
        "buyer": {
            "company_name": "APGENCO",
            "email": "buyer@example.in",
            "gstin": "37AACCA2734J1ZR",
        },
        "supplier": {
            "company_name": "Jyothi Rubber Udyog",
            "email": "supplier@example.com",
        },
        "rfq_number": "M100028013",
        "rfq_issue_date": "2025-05-31",
        "quotation_due_date": "2025-06-30",
        "items": [
            {
                "quantity": 50,
                "unit_price": 3950.0,
                "line_total": 197500.0,
            }
        ],
        "delivery_requirements": {"delivery_location": "RTPP Stores"},
        "conflicts": [],
    }


def test_calculated_confidence_is_high_for_verified_payload():
    result = audit_procurement_completeness(_complete_rfq_payload())

    assert result["llm_confidence_score"] == 0.95
    assert result["calculated_confidence_score"] > 0.9
    assert result["confidence_discrepancy_flag"] is False
    assert "confidence_score" not in result


def test_bad_gstin_and_nonreconciling_total_reduce_confidence_and_flag_discrepancy():
    payload = deepcopy(_complete_rfq_payload())
    payload["llm_confidence_score"] = 0.98
    payload["buyer"]["gstin"] = "not-a-gstin"
    payload["items"][0]["line_total"] = 197499.0

    result = audit_procurement_completeness(payload)

    assert result["calculated_confidence_score"] < 0.7
    assert result["confidence_discrepancy_flag"] is True
