"""
Unit Tests for Token Efficiency Infrastructure.
Verifies preflight quota checks, 429 error metric parsing, and multi-file attachment batching.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock
from tools.token_tracker import (
    load_token_usage, save_token_usage, update_usage_from_429_error,
    check_preflight_quota, record_successful_usage
)
from tools.intelligent_extractor.orchestrator import PipelineOrchestrator


def test_update_usage_from_429_error():
    """Verify regex parsing of Used X and Limit Y from 429 error body."""
    err_str = "Error 429: Rate limit exceeded. Used 99989 tokens, Limit 100000 tokens per day. Please try again."
    used, limit = update_usage_from_429_error(err_str)
    assert used == 99989
    assert limit == 100000

    usage_data = load_token_usage()
    assert usage_data["used_tokens"] == 99989
    assert usage_data["limit_tokens"] == 100000


def test_preflight_quota_check_fails_fast():
    """Verify preflight check returns False when estimated cost + used >= limit."""
    data = load_token_usage()
    data["used_tokens"] = 99500
    data["limit_tokens"] = 100000
    save_token_usage(data)

    # 600 estimated tokens should exceed 100,000 limit
    assert check_preflight_quota(600) is False
    assert check_preflight_quota(300) is True


def test_single_call_attachment_batching(tmp_path, monkeypatch):
    """Verify multiple attachments are processed individually with file headers."""
    f1 = tmp_path / "PO.pdf"
    f2 = tmp_path / "Specs.xlsx"
    f1.write_bytes(b"%PDF-1.4 PO content batch test")
    f2.write_bytes(b"PK\x03\x04 Specs content batch test")

    orchestrator = PipelineOrchestrator()
    metadata = {"subject": "PO and Specs Batch Test", "sender": "procurement@client.com"}

    mock_extract = MagicMock(return_value={
        "extraction_status": "success",
        "intent": "purchase_order_issuance",
        "buyer": {"company_name": "Client Corp"},
        "supplier": {"company_name": "Supplier Inc"},
        "items": [],
        "confidence_score": 0.95
    })
    monkeypatch.setattr(orchestrator.extractor, "extract", mock_extract)
    monkeypatch.setattr(orchestrator.classifier, "classify", lambda ctx: MagicMock(intent="purchase_order_issuance", confidence=0.95))

    orchestrator.run(metadata, "Order details attached", [f1, f2])

    # Assert extract was called twice (once for each file)
    assert mock_extract.call_count == 2
    
    passed_ctx_1 = mock_extract.call_args_list[0][0][0]
    passed_ctx_2 = mock_extract.call_args_list[1][0][0]
    
    assert "=== ATTACHMENT: PO.pdf ===" in passed_ctx_1 or "=== FILE: PO.pdf ===" in passed_ctx_1
    assert "=== ATTACHMENT: Specs.xlsx ===" in passed_ctx_2 or "=== FILE: Specs.xlsx ===" in passed_ctx_2
