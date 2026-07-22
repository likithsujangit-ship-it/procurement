import pytest
import json
from pathlib import Path
from tools.intelligent_extractor.validate_extraction import validate_extraction

@pytest.fixture
def rfq_payload():
    return {
      "intent": "request_for_quotation",
      "document_type": ["RFQ", "Technical_Specification"],
      "buyer": {
        "company_name": "Acme Corp",
        "contact_name": "John Doe",
        "contact_title": "Procurement Manager",
        "email": "john@acme.com",
        "phone": "1234567890",
        "address": "123 Factory Lane",
        "gstin": "27ABCDE1234F1Z5"
      },
      "supplier": {
        "company_name": "Supplier Inc",
        "contact_name": "Jane Smith",
        "contact_title": "Sales Lead",
        "email": "jane@supplier.com",
        "address": "456 Warehouse Blvd"
      },
      "rfq_number": "RFQ-2026-001",
      "rfq_date": "2026-07-20",
      "quotation_due_date": "2026-08-01",
      "items": [
        {
          "part_number": "PN123",
          "description": "Steel Widget",
          "quantity": 100,
          "unit": "pcs",
          "material_spec": "ASTM A216 WCB"
        }
      ],
      "commercial_terms": {
        "payment_terms": "Net 30",
        "incoterms": "FOB",
        "currency": "USD",
        "warranty": "1 Year",
        "delivery_requirement": "Within 30 days"
      },
      "shipping_details": {},
      "attachments": [
        {
          "filename": "specs.pdf",
          "type": "Technical_Specification",
          "contains": ["item list", "commercial terms"]
        }
      ],
      "missing_fields": ["insurance_terms"],
      "conflicts": [],
      "confidence_score": 0.95
    }

@pytest.fixture
def po_payload():
    return {
      "intent": "purchase_order",
      "document_type": ["Purchase_Order"],
      "buyer": {
        "company_name": "Acme Corp",
        "contact_name": "John Doe",
        "contact_title": "Procurement Manager",
        "email": "john@acme.com",
        "phone": "1234567890",
        "address": "123 Factory Lane",
        "gstin": "27ABCDE1234F1Z5"
      },
      "supplier": {
        "company_name": "Supplier Inc",
        "contact_name": "Jane Smith",
        "contact_title": "Sales Lead",
        "email": "jane@supplier.com",
        "address": "456 Warehouse Blvd"
      },
      "po_number": "PO-2026-1182",
      "po_date": "2026-07-20",
      "reference_rfq_number": "RFQ-2026-001",
      "approval_status": "approved",
      "items": [
        {
          "part_number": "PN123",
          "description": "Steel Widget",
          "quantity": 100,
          "unit": "pcs",
          "material_spec": "ASTM A216 WCB"
        }
      ],
      "commercial_terms": {
        "payment_terms": "Net 30",
        "incoterms": "FOB",
        "currency": "USD",
        "total_order_value": 15000.0,
        "delivery_schedule": "Immediate"
      },
      "shipping_details": {},
      "attachments": [
        {
          "filename": "Purchase_Order_123.pdf",
          "type": "Purchase_Order",
          "contains": ["po details"]
        }
      ],
      "missing_fields": [],
      "conflicts": [],
      "confidence_score": 0.98
    }

def test_valid_rfq_payload(rfq_payload):
    is_valid, errors, warnings, schema = validate_extraction(rfq_payload)
    assert is_valid is True
    assert len(errors) == 0
    assert schema == "request_for_quotation_schema.json"

def test_valid_po_payload(po_payload):
    is_valid, errors, warnings, schema = validate_extraction(po_payload)
    assert is_valid is True
    assert len(errors) == 0
    assert schema == "purchase_order_schema.json"

def test_invalid_date_format(rfq_payload):
    rfq_payload["rfq_date"] = "20-Jul-2026"
    is_valid, errors, warnings, schema = validate_extraction(rfq_payload)
    assert is_valid is False
    assert any("not a valid calendar date" in err or "does not match format" in err for err in errors)

def test_float_quantity(rfq_payload):
    rfq_payload["items"][0]["quantity"] = 100.0
    is_valid, errors, warnings, schema = validate_extraction(rfq_payload)
    assert is_valid is False
    assert any("expected integer" in err or "is not of type 'integer'" in err for err in errors)

def test_cross_field_attachment_type(rfq_payload):
    rfq_payload["attachments"][0]["type"] = "BOM"
    is_valid, errors, warnings, schema = validate_extraction(rfq_payload)
    assert is_valid is False
    assert any("not in document_type array" in err for err in errors)

def test_unknown_missing_field_warning(rfq_payload):
    rfq_payload["missing_fields"].append("project_code")
    is_valid, errors, warnings, schema = validate_extraction(rfq_payload)
    assert is_valid is True
    assert any("project_code" in w for w in warnings)

def test_purchase_order_filename_sanity_warning(po_payload):
    po_payload["document_type"].append("Delivery_Schedule")
    po_payload["attachments"].append({
        "filename": "Purchase_Order_123.pdf",
        "type": "Delivery_Schedule",
        "contains": ["po details"]
    })
    is_valid, errors, warnings, schema = validate_extraction(po_payload)
    # The file type isn't Purchase_Order, so it should trigger a warning
    assert any("strongly implies 'Purchase_Order'" in w for w in warnings)


def test_completeness_po_scoring(po_payload):
    from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness
    # Make po_payload completely complete
    po_payload["po_number"] = "PO-123"
    po_payload["po_date"] = "2026-07-20"
    po_payload["buyer"]["company_name"] = "Acme Corp"
    po_payload["supplier"]["company_name"] = "Supplier Inc"
    po_payload["items"] = [{"quantity": 10}]
    po_payload["commercial_terms"] = {
        "payment_terms": "Net 30",
        "gst_rate": "18%",
        "tds_rate": "2%",
        "security_deposit": "2.5%",
        "performance_bank_guarantee": "10%",
        "liquidated_damages": "5%",
        "delivery_requirement": "30 days"
    }
    po_payload["delivery_requirements"] = {
        "required_delivery_date": "30 days",
        "delivery_location": "Stores"
    }
    po_payload["approval"] = "Approved"
    po_payload["confidence_score"] = 0.98  # Penalty of 0
    po_payload["conflicts"] = []           # Penalty of 0
    
    result = audit_procurement_completeness(po_payload)
    completeness = result["completeness"]
    assert completeness["score"] == 100
    assert completeness["status"] == "COMPLETE"
    assert completeness["required_fields"] == 13
    assert completeness["present_fields"] == 13
    assert completeness["missing_fields"] == 0


def test_completeness_rfq_scoring_with_penalties(rfq_payload):
    from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness
    # RFQ required: ["rfq_number", "buyer.company_name", "supplier.company_name", "rfq_issue_date", "quotation_due_date", "items", "delivery_requirements"]
    rfq_payload["rfq_number"] = "RFQ-123"
    rfq_payload["rfq_date"] = "2026-07-20" # matches rfq_issue_date check
    rfq_payload["quotation_due_date"] = "2026-08-01"
    rfq_payload["buyer"]["company_name"] = "Acme Corp"
    rfq_payload["supplier"]["company_name"] = "Supplier Inc"
    rfq_payload["items"] = [{"quantity": 10}]
    # Leave out delivery_requirements (missing 1 field) -> raw_score = (6/7) * 100 = 85.7%
    rfq_payload["delivery_requirements"] = {}
    
    # Introduce confidence penalty: confidence 0.80 -> penalty 10
    rfq_payload["confidence_score"] = 0.80
    
    # Introduce 1 critical conflict -> penalty 10
    rfq_payload["conflicts"] = [{"field": "buyer_email", "severity": "critical"}]
    
    result = audit_procurement_completeness(rfq_payload)
    completeness = result["completeness"]
    # raw_score (85.7) - conflict_penalty (10) - confidence_penalty (10) = 65.7 -> rounded to 66
    assert completeness["score"] == 66
    assert completeness["status"] == "PARTIAL"
    assert completeness["required_fields"] == 7
    assert completeness["present_fields"] == 6
    assert completeness["missing_fields"] == 1
    assert completeness["conflicts"] == 1


def test_optional_contact_title_is_not_reported_as_missing(rfq_payload):
    from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness

    rfq_payload["supplier"].pop("contact_title")
    rfq_payload["missing_fields"] = ["supplier.contact_title"]

    result = audit_procurement_completeness(rfq_payload)

    assert "supplier.contact_title" not in result["missing_fields"]
    assert "supplier.contact_title" in result["optional_fields_missing"]


def test_envelope_mismatch_is_visible_but_does_not_reduce_completeness(rfq_payload):
    from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness

    rfq_payload["delivery_requirements"] = {"delivery_location": "Acme Receiving"}
    rfq_payload["llm_confidence_score"] = 0.98
    rfq_payload["conflicts"] = [{
        "field": "sender_vs_buyer_email",
        "email_sender": "forwarder@example.com",
        "document_buyer_email": "john@acme.com",
    }]

    result = audit_procurement_completeness(rfq_payload)

    assert result["conflicts"][0]["category"] == "envelope_mismatch"
    assert result["completeness"]["score"] == 100
    assert result["completeness"]["status"] == "COMPLETE"


def test_data_conflict_keeps_the_existing_severity_penalty(rfq_payload):
    from tools.intelligent_extractor.validate_procurement import audit_procurement_completeness

    rfq_payload["delivery_requirements"] = {"delivery_location": "Acme Receiving"}
    rfq_payload["llm_confidence_score"] = 0.98
    rfq_payload["conflicts"] = [{
        "field": "items[0].unit_price",
        "category": "data_conflict",
        "source_values": {"rfq": 3950, "vendor_quote": 4100},
    }]

    result = audit_procurement_completeness(rfq_payload)

    assert result["conflicts"][0]["category"] == "data_conflict"
    assert result["completeness"]["score"] == 90
    assert result["completeness"]["status"] == "MOSTLY_COMPLETE"
