"""
Unit Tests for Compound Extension Routing and Empty Extraction Safety Net.
Verifies that files named like test.xlsx.txt and test.pdf.txt route to excel_reader.py
and pdf_reader.py respectively, and not treated as plain text.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tools.extractor import detect_true_suffix, extract_attachment_content


def test_test_xlsx_txt_routing(tmp_path):
    """Assert test.xlsx.txt routes as .xlsx."""
    file_path = tmp_path / "test.xlsx.txt"
    file_path.write_bytes(b"PK\x03\x04")  # Zip header
    
    suffix = detect_true_suffix(file_path, ".txt")
    assert suffix == ".xlsx"


def test_test_pdf_txt_routing(tmp_path):
    """Assert test.pdf.txt routes as .pdf."""
    file_path = tmp_path / "test.pdf.txt"
    file_path.write_bytes(b"%PDF-1.4 header")
    
    suffix = detect_true_suffix(file_path, ".txt")
    assert suffix == ".pdf"


@patch("tools.extractor.extract_excel_text")
def test_test_xlsx_txt_dispatches_to_excel_reader(mock_excel, tmp_path):
    """Assert extract_attachment_content calls extract_excel_text for test.xlsx.txt."""
    mock_excel.return_value = "Row 1: Item A | Qty 10"
    file_path = tmp_path / "test.xlsx.txt"
    file_path.write_bytes(b"PK\x03\x04")
    
    content = extract_attachment_content(file_path)
    assert mock_excel.called
    assert content == "Row 1: Item A | Qty 10"


@patch("tools.extractor.extract_pdf_text")
def test_test_pdf_txt_dispatches_to_pdf_reader(mock_pdf, tmp_path):
    """Assert extract_attachment_content calls extract_pdf_text for test.pdf.txt."""
    mock_pdf.return_value = "Invoice #1001 Total $500"
    file_path = tmp_path / "test.pdf.txt"
    file_path.write_bytes(b"%PDF-1.4 header")
    
    content = extract_attachment_content(file_path)
    assert mock_pdf.called
    assert content == "Invoice #1001 Total $500"
