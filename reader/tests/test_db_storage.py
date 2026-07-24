import os
import pytest
from pathlib import Path
from db.db import get_or_create_supplier, get_or_create_rfq, insert_quotation, get_comparison_grid
from db.storage import save_attachment


def test_db_operations():
    # 1. Supplier creation and deduplication
    s_id = get_or_create_supplier(name="M/s Test Supplier", email="test@supplier.com")
    assert s_id is not None
    s_id_dup = get_or_create_supplier(name="M/s Test Supplier", email="test@supplier.com")
    assert s_id == s_id_dup

    # 2. RFQ creation and deduplication
    rfq_id = get_or_create_rfq(rfq_number="RFQ-TEST-999", part_description="Test Item Description")
    assert rfq_id is not None
    rfq_id_dup = get_or_create_rfq(rfq_number="RFQ-TEST-999")
    assert rfq_id == rfq_id_dup

    # 3. Quotation insertion
    q_fields = {
        "price": 125000.0,
        "currency": "INR",
        "moq": 10.0,
        "lead_time_days": 15,
        "payment_terms": "30 days net",
        "validity": "31-12-2026",
        "confidence_score": 0.95
    }
    q_id = insert_quotation(rfq_id=rfq_id, supplier_id=s_id, extracted_fields=q_fields)
    assert q_id is not None

    # 4. Comparison grid verification
    grid = get_comparison_grid("RFQ-TEST-999")
    assert len(grid) == 1
    assert grid[0]["supplier"] == "M/s Test Supplier"
    assert grid[0]["price"] == 125000.0


def test_blob_storage(tmp_path):
    # Call save_attachment with mock data
    test_bytes = b"Hello, this is a mock attachment file content for testing content hashing."
    filename = "test_document.pdf"
    sender = "sender@domain.com"
    
    # Save the file first time
    res = save_attachment(
        raw_bytes=test_bytes,
        original_filename=filename,
        sender_email=sender,
        mime_type="application/pdf"
    )
    
    assert res["sha256"] is not None
    assert res["is_duplicate"] is False
    assert res["document_id"] is not None
    assert os.path.exists(res["path"])
    
    # Save the file second time (duplicate)
    res_dup = save_attachment(
        raw_bytes=test_bytes,
        original_filename=filename,
        sender_email=sender,
        mime_type="application/pdf"
    )
    
    assert res_dup["sha256"] == res["sha256"]
    assert res_dup["is_duplicate"] is True
    assert res_dup["document_id"] == res["document_id"]
    assert res_dup["path"] == res["path"]
