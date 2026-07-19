"""
Archive (ZIP/RAR) Content Listing Module.
Extracts and lists filenames and directory structures from archive files.
"""

from pathlib import Path
import zipfile
from tools.utils import setup_logger

logger = setup_logger("zip_reader")


def extract_archive_filenames(filepath: Path) -> str:
    """
    Lists all files and directories contained within a ZIP or RAR archive.
    Provides troubleshooting fallbacks for RAR archives.
    
    Args:
        filepath: Path to the archive file on disk.
        
    Returns:
        A list of archived files formatted as a string.
    """
    suffix = filepath.suffix.lower()
    logger.info(f"Listing files in archive: {filepath.name} ({suffix})")
    
    # 1. Handle ZIP archives
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(filepath, "r") as zip_ref:
                infolist = zip_ref.infolist()
                if not infolist:
                    return "[ZIP Archive is empty]"
                    
                file_details = []
                for info in infolist:
                    # Size formatting
                    size_kb = round(info.file_size / 1024, 2)
                    is_dir = "/" if info.filename.endswith("/") else ""
                    file_details.append(f"- {info.filename} ({size_kb} KB){is_dir}")
                    
                return "\n".join(file_details)
        except Exception as e:
            logger.error(f"Error reading ZIP {filepath.name}: {e}")
            return f"[Error reading ZIP archive: {e}]"
            
    # 2. Handle RAR archives (RAR requires external libraries and tools)
    elif suffix == ".rar":
        logger.warning(f"File {filepath.name} is a RAR archive. Native python zipfile library does not support RAR.")
        return (
            "[Unsupported Format: RAR Archive]\n"
            "Troubleshooting: Reading RAR files in pure Python requires the external 'rarfile' library "
            "and the 'unrar' terminal utility. Please extract the files manually or re-package "
            "the files as a standard .zip archive."
        )
        
    else:
        return f"[Unsupported Archive Format: {suffix}]"
