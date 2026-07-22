"""
Unit & Integration Tests for Extraction Failure State Machine.
Verifies that when all Groq API calls fail (429 Rate Limit), the pipeline returns
extraction_status="failed" with null values for buyer, supplier, items, and confidence_score.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from tools.intelligent_extractor.orchestrator import PipelineOrchestrator
from tools.intelligent_extractor.entity_extractor import EntityExtractor


def test_consecutive_groq_429_failures(tmp_path, monkeypatch):
    """Mocks consecutive Groq 429 rate limit errors and asserts failure state and null fields."""
    sample_file = tmp_path / "PO_sample.pdf"
    sample_file.write_bytes(b"%PDF-1.4 sample content")
    
    orchestrator = PipelineOrchestrator()
    
    # Mock groq_client in entity_extractor to simulate 429 errors across all models
    def mock_get_chat_completion(*args, **kwargs):
        raise Exception("Error code: 429 - Rate limit reached for model in organization on tokens per day (TPD)")

    monkeypatch.setattr(orchestrator.extractor.llm, "get_chat_completion", mock_get_chat_completion)
    
    # Mock classifier to avoid API calls during test
    mock_classification = MagicMock()
    mock_classification.intent = "purchase_order_issuance"
    mock_classification.confidence = 0.90
    monkeypatch.setattr(orchestrator.classifier, "classify", lambda ctx: mock_classification)
    
    metadata = {
        "subject": "PO 98765 Order",
        "sender": "supplier@testcorp.com",
        "date": "Mon, 21 Jul 2026 10:00:00 +0000"
    }
    
    result = orchestrator.run(metadata, "Please process attached PO", [sample_file])
    
    # Assert state machine status
    assert result.get("extraction_status") == "failed"
    assert "429" in str(result.get("failure_reason")) or "Rate limit" in str(result.get("failure_reason"))
    
    # Assert strict null fields
    assert result.get("buyer") is None
    assert result.get("supplier") is None
    assert result.get("items") is None
    assert result.get("confidence_score") is None
    assert result.get("procurement_status", {}).get("status") == "FAILED"
    assert result.get("procurement_status", {}).get("completeness_score") == 0
