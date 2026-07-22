"""
Unit tests for Precision Fixes across merger, orchestrator, entity_extractor, and validate_extraction.
"""

import pytest
from tools.intelligent_extractor.merger import truncate_text
from tools.intelligent_extractor.orchestrator import run_pre_extraction_pass
from tools.intelligent_extractor.validate_extraction import is_valid_date, validate_extraction


def test_structure_aware_truncation():
    """Validates that structure-aware truncation preserves tabular lines over narrative text."""
    sample_text = (
        "Dear Purchasing Manager,\n"
        "We are pleased to submit our formal quotation for your review.\n"
        "Please find the detailed commercial break down attached below.\n"
        "=== TABLE OF ITEMS ===\n"
        "Item | Qty | Part Number | Unit Price | Total\n"
        "Widget A | 50 | WDG-101 | $10.00 | $500.00\n"
        "Widget B | 100 | WDG-102 | $20.00 | $2000.00\n"
        "=== END TABLE ===\n"
        "Thank you for considering our offer. Please let us know if you need any additional information.\n"
        "Sincerely,\n"
        "Sales Department\n"
    )
    
    # Force small character budget so truncation triggers
    truncated = truncate_text(sample_text, max_tokens=65)
    
    # Assert table lines are preserved
    assert "Widget A | 50 | WDG-101 | $10.00 | $500.00" in truncated
    assert "Widget B | 100 | WDG-102 | $20.00 | $2000.00" in truncated
    assert "=== TABLE OF ITEMS ===" in truncated


def test_pre_extraction_pass():
    """Validates heuristic regex extraction of dates, GSTINs, emails, and phones."""
    raw_text = (
        "Invoice Date: 2026-07-21\n"
        "GSTIN: 27AAPCU2056U1ZV\n"
        "Contact: accounts@vendor.com or +91 9876543210\n"
        "Ref PO: PO-889922\n"
    )
    hints = run_pre_extraction_pass(raw_text)
    
    assert "2026-07-21" in hints.get("dates", [])
    assert "27AAPCU2056U1ZV" in hints.get("gstins", [])
    assert "accounts@vendor.com" in hints.get("emails", [])
    assert "PO-889922" in hints.get("document_ids", [])


def test_date_and_quantity_validation_precision():
    """Validates date formats (ISO & YYYY-MM-DD) and integer quantity handling."""
    assert is_valid_date("2026-07-21")
    assert is_valid_date("2026-07-21T09:16:43+05:30")
    assert is_valid_date("2026/07/21")

    data = {
        "intent": "request_for_quotation",
        "rfq_date": "2026-07-21T09:16:43+05:30",
        "items": [
            {"description": "Item 1", "quantity": 10}
        ]
    }
    
    is_valid, errors, warnings, schema_used = validate_extraction(data)
    assert is_valid
    assert data["items"][0]["quantity"] == 10

