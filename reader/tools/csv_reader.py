"""
CSV File Content Extraction Module.
Reads rows from comma-separated values files using standard library csv module.
"""

import csv
from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("csv_reader")


def extract_csv_text(filepath: Path) -> str:
    """
    Extracts text from all rows in a CSV file.
    
    Args:
        filepath: Path to the CSV file on disk.
        
    Returns:
        Formatted CSV rows as a string.
    """
    logger.info(f"Extracting rows from CSV: {filepath.name}")
    
    try:
        # Detect encoding or fallback to utf-8
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            logger.debug("UTF-8 decoding failed. Falling back to latin-1 encoding.")
            with open(filepath, "r", encoding="latin-1") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
        if not rows:
            return "[CSV file is empty]"
            
        formatted_rows = []
        for i, row in enumerate(rows):
            cleaned_row = [cell.strip() for cell in row]
            formatted_rows.append(f"Row {i + 1}: " + " | ".join(cleaned_row))
            
        return "\n".join(formatted_rows)

    except Exception as e:
        logger.error(f"Error reading CSV {filepath.name}: {e}")
        return f"[Error reading CSV file: {e}]"
