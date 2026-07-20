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
