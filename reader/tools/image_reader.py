"""
Image OCR Module.
Extracts textual content from images using pytesseract (Tesseract OCR) and PIL.
"""

from pathlib import Path
from PIL import Image
import pytesseract
from tools.utils import setup_logger

logger = setup_logger("image_reader")


def extract_image_text(filepath: Path) -> str:
    """
    Performs OCR (Optical Character Recognition) on an image file.
    
    Args:
        filepath: Path to the image file on disk.
        
    Returns:
        Extracted text content from the image, or detailed error message.
    """
    logger.info(f"Performing OCR on image: {filepath.name}")
    
    try:
        # Load image via Pillow
        img = Image.open(filepath)
        
        # Run OCR
        text = pytesseract.image_to_string(img)
        
        cleaned_text = text.strip()
        if not cleaned_text:
            logger.warning(f"OCR returned empty string for image: {filepath.name}")
            return "[OCR Completed - No text detected in image]"
            
        return cleaned_text

    except pytesseract.TesseractNotFoundError as t_err:
        logger.error(f"Tesseract OCR is not installed or not in PATH: {t_err}")
        return (
            "[OCR Error: Tesseract Engine Not Found]\n"
            "Troubleshooting: This feature requires Tesseract OCR installed on the system.\n"
            "- macOS: Install via Homebrew: 'brew install tesseract'\n"
            "- Windows: Download installer from UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki) "
            "and add the install directory (typically C:\\Program Files\\Tesseract-OCR) to your System PATH."
        )
    except Exception as e:
        logger.error(f"Error performing OCR on image {filepath.name}: {e}")
        return f"[Error processing image file: {e}]"
