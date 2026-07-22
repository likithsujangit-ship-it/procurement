"""
Tests for Content-Aware File Sniffing, Image Preprocessing, and Embedded Image OCR.
"""

import io
import pytest
from pathlib import Path
from PIL import Image, ImageDraw

from tools.utils import preprocess_image_for_ocr
from tools.extractor import detect_true_suffix, extract_attachment_content


def create_sample_image() -> Image.Image:
    """Creates a simple PIL image containing text for testing."""
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "TEST OCR", fill=(0, 0, 0))
    return img


def test_image_preprocessing():
    """Validates that preprocess_image_for_ocr upscales low DPI images and binarizes."""
    img = create_sample_image()
    img.info["dpi"] = (72, 72)
    
    processed = preprocess_image_for_ocr(img)
    # Target DPI is 150, so 150 / 72 = ~2.08 upscale
    assert processed.width > img.width
    assert processed.mode in ("L", "1")


def test_file_type_sniffing_mismatch(tmp_path: Path):
    """Tests that a PDF file named with a .doc extension is detected as a PDF."""
    fake_doc_path = tmp_path / "invoice_scanned.doc"
    # Write PDF magic bytes header
    fake_doc_path.write_bytes(b"%PDF-1.4 header contents")

    true_ext = detect_true_suffix(fake_doc_path, ".doc")
    assert true_ext == ".pdf"


def test_file_type_sniffing_matching(tmp_path: Path):
    """Tests that a PDF file named with a .pdf extension is correctly retained."""
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 header contents")

    true_ext = detect_true_suffix(pdf_path, ".pdf")
    assert true_ext == ".pdf"
