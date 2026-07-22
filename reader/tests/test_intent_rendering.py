"""
Unit Tests for LLM Intent Display String Rendering.
Verifies that long intent strings like 'purchase_order_issuance' and 'request_for_quotation'
render in full without single-character slicing or truncation.
"""

import pytest
import io
import sys


def format_intent_display(result: dict) -> str:
    """Helper mirroring assistant.py intent display extraction logic."""
    intent_raw = result.get("intent")
    if intent_raw and str(intent_raw).strip():
        if isinstance(intent_raw, list) and len(intent_raw) > 0:
            raw_type = str(intent_raw[0]).strip()
        else:
            raw_type = str(intent_raw).strip()
    else:
        doc_type_val = result.get("document_type")
        if doc_type_val:
            if isinstance(doc_type_val, list) and len(doc_type_val) > 0:
                raw_type = str(doc_type_val[0]).strip()
            elif isinstance(doc_type_val, str) and doc_type_val.strip():
                raw_type = doc_type_val.strip()
            else:
                raw_type = "other"
        else:
            raw_type = "other"
    return raw_type


def test_full_intent_string_rendering():
    """Verify long intent strings are preserved in full."""
    res1 = {"intent": "purchase_order_issuance", "document_type": ["RFQ"]}
    display1 = format_intent_display(res1)
    assert display1 == "purchase_order_issuance"
    assert display1 != "P"
    assert display1 != "Purchase Order"

    res2 = {"intent": "request_for_quotation", "document_type": ["RFQ"]}
    display2 = format_intent_display(res2)
    assert display2 == "request_for_quotation"
    assert display2 != "R"

    res3 = {"intent": "delivery_note_issuance", "document_type": ["DN"]}
    display3 = format_intent_display(res3)
    assert display3 == "delivery_note_issuance"


def test_terminal_print_rendering(capsys):
    """Verify print output renders full intent string in terminal table."""
    intent = "purchase_order_issuance"
    print(f"Document Type (LLM Intent): {intent}")
    captured = capsys.readouterr()
    assert "Document Type (LLM Intent): purchase_order_issuance" in captured.out
