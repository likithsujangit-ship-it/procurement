"""
PDF Content Extraction Module.
Reads text content from PDF files using pypdf, PyMuPDF (fitz), pdfplumber, and Tesseract OCR for scanned images.
"""

from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("pdf_reader")


def extract_pdf_text(filepath: Path) -> str:
    """
    Extracts all text content from a PDF file using pypdf, PyMuPDF (fitz), and OCR for scanned PDFs.
    
    Args:
        filepath: Path to the PDF file on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from PDF: {filepath.name}")
    text_parts = []

    # 1. Try PyMuPDF (fitz) first - superior layout & text preservation
    try:
        import fitz
        doc = fitz.open(filepath)
        for i, page in enumerate(doc):
            p_text = page.get_text("text").strip()
            if p_text:
                text_parts.append(f"--- Page {i + 1} ---\n{p_text}")
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed for {filepath.name}: {e}")

    # 2. Try pypdf as second text extraction engine if PyMuPDF yielded little/no text
    if not text_parts or sum(len(t) for t in text_parts) < 30:
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            pypdf_parts = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    pypdf_parts.append(f"--- Page {i + 1} ---\n{page_text.strip()}")
            if pypdf_parts:
                text_parts = pypdf_parts
        except Exception as e:
            logger.warning(f"pypdf extraction failed for {filepath.name}: {e}")

    # 3. Try pdfplumber as third text extraction engine
    if not text_parts or sum(len(t) for t in text_parts) < 30:
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                plumber_parts = []
                for i, page in enumerate(pdf.pages):
                    pt = page.extract_text()
                    if pt and pt.strip():
                        plumber_parts.append(f"--- Page {i + 1} ---\n{pt.strip()}")
                if plumber_parts:
                    text_parts = plumber_parts
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed for {filepath.name}: {e}")

    # 4. Fall back to Tesseract OCR if text is minimal (Scanned image PDF)
    total_extracted_len = sum(len(t) for t in text_parts)
    if total_extracted_len < 30:
        logger.info(f"PDF {filepath.name} appears to be a scanned image (text len < 30). Running OCR fallback...")
        ocr_parts = []
        try:
            import fitz
            import pytesseract
            from PIL import Image
            import io

            doc = fitz.open(filepath)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = pytesseract.image_to_string(img).strip()
                if ocr_text:
                    ocr_parts.append(f"--- Page {i + 1} (OCR) ---\n{ocr_text}")
            doc.close()
            
            if ocr_parts:
                logger.info(f"Successfully extracted text via Tesseract OCR for scanned PDF: {filepath.name}")
                return "\n\n".join(ocr_parts)
        except Exception as ocr_err:
            logger.error(f"OCR fallback failed for {filepath.name}: {ocr_err}")

    if not text_parts:
        logger.warning(f"No text extracted from PDF: {filepath.name}.")
        return "[PDF Empty or Scanned Image - No readable text found]"
        
    return "\n\n".join(text_parts)
