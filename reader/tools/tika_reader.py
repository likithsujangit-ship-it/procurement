from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("tika_reader")

def extract_tika_text(filepath: Path) -> str:
    """
    Extracts text from legacy document formats (.doc, .rtf, .odt, .ods) using Apache Tika.
    Requires Java to be installed on the host machine.
    
    Args:
        filepath: Path to the target file on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting legacy text with Tika: {filepath.name}")
    
    try:
        import tika
        tika.initVM() # Ensure Tika VM starts
        from tika import parser
        
        parsed = parser.from_file(str(filepath))
        text = parsed.get("content", "")
        
        if not text or not text.strip():
            return f"[{filepath.suffix.upper()} Document is empty or unreadable]"
            
        return text.strip()
    except Exception as e:
        logger.error(f"Error reading legacy file {filepath.name} with Tika: {e}")
        return f"[Error reading legacy file: {e}]"
