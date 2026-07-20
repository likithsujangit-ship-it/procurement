"""
Word Document (DOCX/DOC) Content Extraction Module.
Reads paragraphs and tables from .docx (python-docx) and legacy .doc files (olefile / binary stream text parser).
"""

import re
from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("docx_reader")


def extract_docx_text(filepath: Path) -> str:
    """
    Extracts text from paragraphs and tables in a .docx or legacy .doc file.
    
    Args:
        filepath: Path to the Word document on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from Word document: {filepath.name}")
    suffix = filepath.suffix.lower()

    # 1. Handle legacy .doc files
    if suffix == ".doc":
        try:
            # Try olefile stream extraction
            import olefile
            if olefile.isOleFile(filepath):
                ole = olefile.OleFileIO(filepath)
                if ole.exists("WordDocument"):
                    stream = ole.openstream("WordDocument").read()
                    # Decode stream and extract printable character sequences
                    raw_text = stream.decode("latin-1", errors="ignore")
                    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]+', ' ', raw_text)
                    lines = []
                    for line in cleaned.splitlines():
                        cleaned_line = line.strip()
                        if len(cleaned_line) > 3 and not cleaned_line.startswith("Normal.") and not cleaned_line.startswith("Table "):
                            lines.append(cleaned_line)
                    if lines:
                        logger.info(f"Successfully extracted text from legacy .doc file: {filepath.name}")
                        return "\n".join(lines)
        except Exception as e:
            logger.warning(f"olefile extraction failed for {filepath.name}: {e}")
            
        # Fallback binary text pattern extractor for .doc files
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            raw_text = content.decode("latin-1", errors="ignore")
            cleaned = re.sub(r'[^\x20-\x7E\n\r\t]+', ' ', raw_text)
            lines = [line.strip() for line in cleaned.splitlines() if len(line.strip()) > 4]
            if lines:
                return "\n".join(lines)
        except Exception as e:
            logger.error(f"Fallback binary extraction failed for legacy .doc {filepath.name}: {e}")
            return f"[Error reading legacy .doc file {filepath.name}: {e}]"

    # 2. Handle modern .docx files using python-docx
    try:
        import docx
        doc = docx.Document(filepath)
        text_parts = []
        
        # Extract paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text.strip())
                
        # Extract tables
        for t_idx, table in enumerate(doc.tables):
            text_parts.append(f"\n--- Table {t_idx + 1} ---")
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells]
                if any(row_data):
                    text_parts.append(" | ".join(row_data))
                
        if not text_parts:
            return "[DOCX Document is empty]"
            
        return "\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error reading DOCX {filepath.name}: {e}")
        return f"[Error reading DOCX file: {e}]"
