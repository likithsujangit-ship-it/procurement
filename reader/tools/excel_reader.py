"""
Excel Spreadsheets (XLSX/XLS) Content Extraction Module.
Reads sheets and cells from Excel workbooks using openpyxl and xlrd.
"""

from pathlib import Path
from tools.utils import setup_logger

logger = setup_logger("excel_reader")


def extract_excel_text(filepath: Path) -> str:
    """
    Extracts structured sheet names and cell tables from .xlsx and legacy .xls files.
    
    Args:
        filepath: Path to the Excel spreadsheet on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting sheets from Excel workbook: {filepath.name}")
    suffix = filepath.suffix.lower()

    # 1. Handle legacy .xls files using xlrd
    if suffix == ".xls":
        try:
            import xlrd
            wb = xlrd.open_workbook(filepath)
            text_parts = []
            
            for sheet in wb.sheets():
                text_parts.append(f"--- Sheet: {sheet.name} ---")
                rows_content = []
                for row_idx in range(sheet.nrows):
                    row_vals = [str(sheet.cell_value(row_idx, col_idx)).strip() for col_idx in range(sheet.ncols)]
                    if any(val for val in row_vals):
                        rows_content.append(" | ".join(row_vals))
                        
                if rows_content:
                    text_parts.append("\n".join(rows_content))
                else:
                    text_parts.append("[Empty Sheet]")
                    
            if not text_parts:
                return "[Legacy .xls file has no sheets]"
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Failed to extract text from legacy .xls file {filepath.name} using xlrd: {e}")
            return f"[Error reading legacy .xls file {filepath.name}: {e}]"

    # 2. Handle modern .xlsx files using openpyxl
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, data_only=True)
        text_parts = []
        
        for sheet_name in wb.sheetnames:
            text_parts.append(f"--- Sheet: {sheet_name} ---")
            sheet = wb[sheet_name]
            
            rows_content = []
            for row in sheet.iter_rows(values_only=True):
                if not any(val is not None for val in row):
                    continue
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
        logger.error(f"Error reading Excel file {filepath.name}: {e}")
        return f"[Error reading Excel file: {e}]"
