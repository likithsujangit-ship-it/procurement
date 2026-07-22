"""
Plain Text Document Reader Module.
Extracts text content from genuine .txt files using chardet for encoding detection with fallbacks.
"""

from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("text_reader")


def extract_text_file(filepath: Path) -> str:
    """
    Extracts text from a plain text file using chardet encoding detection with fallbacks.
    
    Args:
        filepath: Path to the .txt file.
        
    Returns:
        Extracted text string.
    """
    if not filepath.exists():
        logger.error(f"Text file not found: {filepath}")
        return f"[File not found: {filepath.name}]"
        
    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read()

        if not raw_bytes.strip():
            logger.info(f"Plain text file '{filepath.name}' is empty.")
            return "[Text file is empty]"

        encoding = None
        confidence = 0.0

        try:
            import chardet
            detected = chardet.detect(raw_bytes)
            encoding = detected.get("encoding")
            confidence = detected.get("confidence", 0.0)
            if encoding:
                logger.info(f"Reading plain text file '{filepath.name}' using detected encoding '{encoding}' (confidence: {confidence:.2f})")
        except ImportError:
            logger.debug("chardet library not installed. Falling back to standard encodings.")

        encodings_to_try = [encoding, "utf-8", "utf-8-sig", "latin-1", "cp1252"] if encoding else ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        content = None
        for enc in encodings_to_try:
            try:
                content = raw_bytes.decode(enc)
                break
            except (UnicodeDecodeError, TypeError):
                continue

        if content is None:
            content = raw_bytes.decode("utf-8", errors="ignore")

        content = content.strip()
        if not content:
            return "[Text file is empty]"

        return content

    except Exception as e:
        logger.error(f"Error reading plain text file {filepath.name}: {e}")
        return f"[Error reading plain text file: {e}]"


def extract_txt_text(filepath: Path) -> str:
    """Alias for extract_text_file for backward compatibility."""
    return extract_text_file(filepath)
