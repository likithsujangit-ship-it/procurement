"""
Excel Spreadsheets (XLSX/XLS) Content Extraction Module.
Reads sheets and cells from Excel workbooks using openpyxl.
"""

from pathlib import Path
import openpyxl
from tools.utils import setup_logger

logger = setup_logger("excel_reader")


def extract_excel_text(filepath: Path) -> str:
    """
    Extracts structured sheet names and cell tables from a .xlsx file.
    Provides troubleshooting fallback for older .xls files.
    
    Args:
        filepath: Path to the Excel spreadsheet on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting sheets from Excel workbook: {filepath.name}")
    
    # Handle older .xls files gracefully
    if filepath.suffix.lower() == ".xls":
        logger.warning(f"File {filepath.name} is a legacy .xls file. openpyxl only supports .xlsx.")
        return (
            "[Unsupported Format: Legacy .xls file]\n"
            "Troubleshooting: Please convert this file to the modern .xlsx format "
            "using Microsoft Excel or LibreOffice to allow automated content reading."
        )

    try:
        # Load workbook (data_only=True to extract resolved formulas rather than formulas code)
        wb = openpyxl.load_workbook(filepath, data_only=True)
        text_parts = []
        
        for sheet_name in wb.sheetnames:
            text_parts.append(f"--- Sheet: {sheet_name} ---")
            sheet = wb[sheet_name]
            
            rows_content = []
            for row in sheet.iter_rows(values_only=True):
                # Filter out completely empty rows
                if not any(val is not None for val in row):
                    continue
                
                # Format cell values cleanly
                row_str = [str(val).strip() if val is not None else "" for val in row]
                rows_content.append(" | ".join(row_str))
                
            if rows_content:
                text_parts.append("\n".join(rows_content))
            else:
                text_parts.append("[Empty Sheet]")
                
        if not text_parts:
            return "[Excel file has no sheets]"
            
        return "\n\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error reading Excel workbook {filepath.name}: {e}")
        return f"[Error reading Excel file: {e}]"
