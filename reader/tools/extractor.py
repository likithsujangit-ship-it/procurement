"""
Attachment Content Extractor Orchestrator.
Determines file type extensions and routes to correct specialized parsing modules.
"""

from pathlib import Path
from tools.utils import setup_logger
from tools.pdf_reader import extract_pdf_text
from tools.docx_reader import extract_docx_text
from tools.ppt_reader import extract_ppt_text
from tools.image_reader import extract_image_text
from tools.excel_reader import extract_excel_text
from tools.csv_reader import extract_csv_text
from tools.zip_reader import extract_archive_filenames

logger = setup_logger("extractor")


def extract_attachment_content(filepath: Path) -> str:
    """
    Extracts text/metadata content from the given file based on its extension.
    
    Args:
        filepath: Path to the target attachment file.
        
    Returns:
        Extracted content as a string.
    """
    if not filepath.exists():
        logger.error(f"Cannot extract content: file does not exist at {filepath}")
        return f"[File not found: {filepath.name}]"
        
    suffix = filepath.suffix.lower()
    logger.info(f"Orchestrating extraction for file: {filepath.name} (type: {suffix})")

    # Route based on file extension suffix
    if suffix == ".pdf":
        return extract_pdf_text(filepath)
        
    elif suffix in (".docx", ".doc"):
        return extract_docx_text(filepath)
        
    elif suffix in (".pptx", ".ppt"):
        return extract_ppt_text(filepath)
        
    elif suffix in (".xlsx", ".xls"):
        return extract_excel_text(filepath)
        
    elif suffix == ".csv":
        return extract_csv_text(filepath)
        
    elif suffix in (".zip", ".rar"):
        return extract_archive_filenames(filepath)
        
    elif suffix in (".png", ".jpeg", ".jpg", ".bmp", ".gif", ".tiff"):
        return extract_image_text(filepath)
        
    elif suffix in (".txt", ".log", ".json", ".md", ".xml", ".html", ".ini", ".yaml", ".yml"):
        # Handle plain text files directly
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if not content:
                return "[Text file is empty]"
            return content
        except Exception as e:
            logger.error(f"Error reading plain text file {filepath.name}: {e}")
            return f"[Error reading plain text file: {e}]"
            
    else:
        logger.warning(f"Unsupported file type for automated extraction: {suffix}")
        return f"[Unsupported File Format '{suffix}' - Filename: {filepath.name}]"
