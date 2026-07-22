"""
Unit Tests for Multi-Vendor Price Comparison Data (vendor_quotes[]).
Verifies that price evaluation sheets with multiple vendor quotes for a single product
are parsed into vendor_quotes[] with correct ranks and selection status.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from tools.intelligent_extractor.entity_extractor import EntityExtractor


@patch("tools.intelligent_extractor.entity_extractor.GroqClient")
def test_vendor_quotes_extraction(mock_groq):
    """Verify that vendor_quotes[] receives all vendor bids, ranks them L1..L4, and selects L1."""
    extractor = EntityExtractor()

    expected_json = json.dumps({
        "intent": "request_for_quotation",
        "document_type": ["RFQ", "Price_Breakdown"],
        "buyer": {
            "company_name": "APGENCO",
            "contact_name": "VeeraSekhar ADE",
            "email": "rtpp.purchase@apgenco.gov.in"
        },
        "supplier": {
            "company_name": "Jyothi Rubber Udyog (India) Limited",
            "contact_name": "Jyoti",
            "email": "jyoti@jyotirubber.com"
        },
        "rfq_number": "M100028013",
        "rfq_issue_date": "2025-05-31",
        "quotation_due_date": "2025-06-30",
        "date_extended_from": "2025-06-19",
        "items": [
            {
                "line": 1,
                "part_number": "200017447",
                "description": "C-JET Fire Fighting Hose",
                "quantity": 50,
                "unit": "NO",
                "unit_price": 3950.0,
                "currency": "INR",
                "line_total": 197500.0,
                "vendor_quotes": [
                    {
                        "vendor_name": "Jyothi Rubber Udyog (India) Limited, Delhi",
                        "quoted_price": 3950.0,
                        "landed_price": 4707.61,
                        "rank": "L1",
                        "is_selected": True
                    },
                    {
                        "vendor_name": "Subham safety solutions, Vishakapatnam",
                        "quoted_price": 6384.0,
                        "landed_price": 7221.58,
                        "rank": "L2",
                        "is_selected": False
                    },
                    {
                        "vendor_name": "RM Enterprises, Ramagundam",
                        "quoted_price": 7280.0,
                        "landed_price": 8235.14,
                        "rank": "L3",
                        "is_selected": False
                    },
                    {
                        "vendor_name": "3S International, Vishakapatnam",
                        "quoted_price": 7770.0,
                        "landed_price": 8789.42,
                        "rank": "L4",
                        "is_selected": False
                    }
                ]
            }
        ],
        "attachments": []
    })

    mock_instance = mock_groq.return_value
    mock_instance.get_chat_completion.return_value = expected_json

    mock_excel_text = """
    PRICE EVALUATION STATEMENT
    SUB: Supply of C-JET Fire Fighting Hose with SS Coupling
    ENQ. No. M100028013-M09/25-26, Dt.31-05-2025.
    Number of Firms responded: 4.0
    s.no. | Description of the Item | Quantity | M/s.Jyothi Rubber Udyog | M/s. Subham safety solutions | M/s. RM Enterprises | M/s. 3S International
    1.0 | 200017447- C-JET Fire Fighting Hose | 50.0 | 3950.0 | 6384.0 | 7280.0 | 7770.0
    """

    result = extractor.extract(mock_excel_text, "request_for_quotation")

    assert result["extraction_status"] == "success"
    items = result.get("items") or []
    assert len(items) == 1

    item = items[0]
    assert item["part_number"] == "200017447"
    assert item["quantity"] == 50
    assert item["unit_price"] == 3950.0
    assert item["line_total"] == 197500.0

    vq = item.get("vendor_quotes") or []
    assert len(vq) == 4

    # Verify ranks and selection
    assert vq[0]["rank"] == "L1"
    assert vq[0]["is_selected"] is True
    assert vq[0]["quoted_price"] == 3950.0
    assert "Jyothi Rubber" in vq[0]["vendor_name"]

    assert vq[1]["rank"] == "L2"
    assert vq[1]["is_selected"] is False
    assert vq[1]["quoted_price"] == 6384.0

    assert vq[2]["rank"] == "L3"
    assert vq[2]["is_selected"] is False
    assert vq[2]["quoted_price"] == 7280.0

    assert vq[3]["rank"] == "L4"
    assert vq[3]["is_selected"] is False
    assert vq[3]["quoted_price"] == 7770.0
