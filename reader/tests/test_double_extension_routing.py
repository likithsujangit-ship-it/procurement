"""
Unit & Regression Tests for Compound Extension Routing, Text Extraction, and Orchestrator Failure Tracking.
Verifies that files named like .xlsx.txt or .pdf.txt route to their true inner extractors and that failed files are tracked.
"""

import pytest
from pathlib import Path
from tools.extractor import detect_true_suffix, extract_attachment_content
from tools.intelligent_extractor.orchestrator import PipelineOrchestrator


def test_compound_extension_xlsx_txt(tmp_path):
    """Test that a .xlsx.txt file routes as .xlsx."""
    file_path = tmp_path / "M28013-Fire_Hoses.xlsx.txt"
    file_path.write_bytes(b"PK\x03\x04")  # Zip header for xlsx
    
    detected_suffix = detect_true_suffix(file_path, ".txt")
    assert detected_suffix == ".xlsx"


def test_compound_extension_pdf_txt(tmp_path):
    """Test that a .pdf.txt file routes as .pdf."""
    file_path = tmp_path / "invoice.pdf.txt"
    file_path.write_bytes(b"%PDF-1.4 header text")
    
    detected_suffix = detect_true_suffix(file_path, ".txt")
    assert detected_suffix == ".pdf"


def test_genuine_txt_file(tmp_path):
    """Test that a genuine .txt file is read correctly with text reader."""
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Purchase Order #12345 for 100 units of widgets.", encoding="utf-8")
    
    content = extract_attachment_content(file_path)
    assert "Purchase Order #12345" in content


def test_orchestrator_failed_files_tracking(tmp_path, monkeypatch):
    """Test that failed files are explicitly included in failed_files in orchestrator output."""
    missing_file = tmp_path / "nonexistent.docx"
    
    # Mock extractor.extract to simulate an extraction payload
    orchestrator = PipelineOrchestrator()
    
    # Mock entity extractor to avoid LLM API calls
    def mock_extract(context, intent, hints=None):
        return {
            "intent": intent,
            "document_type": ["Purchase Order"],
            "buyer": {"company_name": "Acme Corp"},
            "supplier": {"company_name": "Global Tech"},
            "items": [],
            "confidence_score": 0.9
        }
    
    monkeypatch.setattr(orchestrator.extractor, "extract", mock_extract)
    
    metadata = {"subject": "PO Test", "sender": "buyer@acme.com"}
    result = orchestrator.run(metadata, "Please find attached PO", [missing_file])
    
    assert "failed_files" in result
    assert len(result["failed_files"]) == 1
    assert result["failed_files"][0]["filename"] == "nonexistent.docx"
