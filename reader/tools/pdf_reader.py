"""
PDF Content Extraction Module.
Reads text content from PDF files using pypdf.
"""

from pathlib import Path
from pypdf import PdfReader
from tools.utils import setup_logger

logger = setup_logger("pdf_reader")


def extract_pdf_text(filepath: Path) -> str:
    """
    Extracts all text content from a PDF file.
    
    Args:
        filepath: Path to the PDF file on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from PDF: {filepath.name}")
    
    try:
        reader = PdfReader(filepath)
        text_parts = []
        
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
                
        if not text_parts:
            logger.warning(f"No text extracted from PDF: {filepath.name} (possibly scanned image/empty).")
            return "[PDF Empty or Scanned Image - No readable text found]"
            
        return "\n\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error reading PDF {filepath.name}: {e}")
        return f"[Error reading PDF file: {e}]"
