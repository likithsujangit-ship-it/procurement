"""
Word Document (DOCX/DOC) Content Extraction Module.
Reads paragraphs and tables from Word files using python-docx.
"""

from pathlib import Path
import docx
from tools.utils import setup_logger

logger = setup_logger("docx_reader")


def extract_docx_text(filepath: Path) -> str:
    """
    Extracts text from paragraphs and tables in a .docx file.
    Provides troubleshooting fallback for older .doc files.
    
    Args:
        filepath: Path to the Word document on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from DOCX: {filepath.name}")
    
    # Handle older .doc files gracefully
    if filepath.suffix.lower() == ".doc":
        logger.warning(f"File {filepath.name} is a legacy .doc file. python-docx only supports .docx.")
        return (
            "[Unsupported Format: Legacy .doc file]\n"
            "Troubleshooting: Please convert this file to the modern .docx format "
            "using Microsoft Word or LibreOffice to allow automated content reading."
        )
        
    try:
        doc = docx.Document(filepath)
        text_parts = []
        
        # 1. Extract paragraphs
        for i, para in enumerate(doc.paragraphs):
            if para.text.strip():
                text_parts.append(para.text)
                
        # 2. Extract tables if present
        for t_idx, table in enumerate(doc.tables):
            text_parts.append(f"\n--- Table {t_idx + 1} ---")
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells]
                text_parts.append(" | ".join(row_data))
                
        if not text_parts:
            return "[DOCX Document is empty]"
            
        return "\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error reading DOCX {filepath.name}: {e}")
        return f"[Error reading DOCX file: {e}]"
