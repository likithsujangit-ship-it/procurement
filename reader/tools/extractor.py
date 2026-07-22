"""
Attachment Content Extractor Orchestrator.
Determines file type extensions and routes to correct specialized parsing modules.
Handles compound extensions (e.g., .xlsx.txt, .pdf.txt) and MIME sniffing.
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
from tools.tika_reader import extract_tika_text
from tools.email_reader import extract_email_text
from tools.text_reader import extract_text_file

logger = setup_logger("extractor")

MIME_TO_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "image/png": ".png",
    "image/jpeg": ".jpeg",
    "image/jpg": ".jpeg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/zip": ".zip",
    "application/x-rar-compressed": ".rar",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/csv": ".csv",
    "message/rfc822": ".eml",
}

KNOWN_BINARY_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv",
    ".zip", ".rar", ".png", ".jpeg", ".jpg", ".bmp", ".gif", ".tiff",
    ".rtf", ".odt", ".ods", ".eml", ".msg"
}

STRUCTURED_FORMATS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv"
}


def detect_file_signature(filepath: Path) -> str:
    """Detects MIME type or extension by reading magic bytes."""
    # 1. Try python-magic
    try:
        import magic
        mime = magic.from_file(str(filepath), mime=True)
        if mime:
            return mime
    except Exception:
        pass

    # 2. Try puremagic
    try:
        import puremagic
        exts = puremagic.from_file(str(filepath))
        if exts:
            ext = exts[0].extension.lower()
            if ext and not ext.startswith("."):
                ext = "." + ext
            return ext
    except Exception:
        pass

    # 3. Try filetype
    try:
        import filetype
        kind = filetype.guess(str(filepath))
        if kind and kind.mime:
            return kind.mime
    except Exception:
        pass

    # 4. Manual Magic Bytes Header Fallback
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        if header.startswith(b"%PDF"):
            return "application/pdf"
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif header.startswith(b"GIF8"):
            return "image/gif"
        elif header.startswith(b"BM"):
            return "image/bmp"
        elif header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
            return "image/tiff"
        elif header.startswith(b"PK\x03\x04"):
            return "application/zip"
        elif header.startswith(b"\xd0\xcf\11\xe0\xa1\xb1\x1a\xe1"):
            return "application/msword"
    except Exception:
        pass

    return ""


def detect_true_suffix(filepath: Path, declared_suffix: str) -> str:
    """
    Sniffs binary signature magic bytes and checks for compound extensions (e.g. .xlsx.txt)
    to determine the true file extension.
    """
    fname_lower = filepath.name.lower()
    
    # 1. Check for compound extensions (e.g. filename.xlsx.txt or filename.pdf.txt)
    if fname_lower.endswith(".txt"):
        stem = filepath.stem  # Strips trailing .txt
        preceding_ext = Path(stem).suffix.lower()
        if preceding_ext in KNOWN_BINARY_EXTENSIONS:
            logger.info(f"[extractor] Detected compound extension '{filepath.name}' -> routing as {preceding_ext}")
            return preceding_ext

    # 2. Sniff binary signature magic bytes
    sig = detect_file_signature(filepath)
    if not sig:
        return declared_suffix

    if sig.startswith("."):
        detected_suffix = sig
    else:
        detected_suffix = MIME_TO_SUFFIX.get(sig)

    # Zip container fallback for OOXML formats
    if sig == "application/zip" and declared_suffix in (".docx", ".pptx", ".xlsx", ".zip"):
        return declared_suffix

    if detected_suffix and detected_suffix != declared_suffix:
        logger.warning(
            f"File extension mismatch for '{filepath.name}': declared extension is '{declared_suffix}', "
            f"but magic bytes indicate true type '{detected_suffix}' (Signature/MIME: {sig}). "
            f"Routing to '{detected_suffix}' extractor."
        )
        return detected_suffix

    return declared_suffix


def extract_attachment_content(filepath: Path) -> str:
    """
    Extracts text/metadata content from the given file based on its extension/magic bytes.
    Includes a safety net for empty structured text extractions.
    
    Args:
        filepath: Path to the target attachment file.
        
    Returns:
        Extracted content as a string.
    """
    if not filepath.exists():
        logger.error(f"Cannot extract content: file does not exist at {filepath}")
        return f"[File not found: {filepath.name}]"
        
    declared_suffix = filepath.suffix.lower()
    suffix = detect_true_suffix(filepath, declared_suffix)
    logger.info(f"Orchestrating extraction for file: {filepath.name} (effective type: {suffix})")

    content = ""
    # Route based on file extension suffix
    if suffix == ".pdf":
        content = extract_pdf_text(filepath)
        
    elif suffix == ".docx":
        content = extract_docx_text(filepath)
        
    elif suffix in (".pptx", ".ppt"):
        content = extract_ppt_text(filepath)
        
    elif suffix in (".xlsx", ".xls"):
        content = extract_excel_text(filepath)
        
    elif suffix == ".csv":
        content = extract_csv_text(filepath)
        
    elif suffix in (".zip", ".rar"):
        content = extract_archive_filenames(filepath)
        
    elif suffix in (".png", ".jpeg", ".jpg", ".bmp", ".gif", ".tiff"):
        content = extract_image_text(filepath)
        
    elif suffix in (".doc", ".rtf", ".odt", ".ods"):
        content = extract_tika_text(filepath)
        
    elif suffix in (".eml", ".msg"):
        content = extract_email_text(filepath)
        
    elif suffix in (".txt", ".log", ".json", ".md", ".xml", ".html", ".ini", ".yaml", ".yml"):
        content = extract_text_file(filepath)
        
    else:
        logger.warning(f"Unsupported file type for automated extraction: {suffix}")
        return f"[Unsupported File Format '{suffix}' - Filename: {filepath.name}]"

    # Safety net: Check for empty text in structured files
    if suffix in STRUCTURED_FORMATS:
        clean_c = content.strip() if content else ""
        if not clean_c or clean_c.startswith("["):
            logger.warning(f"[extractor] Extracted text is empty for structured file '{filepath.name}'")

    return content
