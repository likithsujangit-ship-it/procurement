"""
Utilities module for EMAIL READER.
Provides date-wise file logging configuration.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from config import Config
import os

# Configure Tesseract path for Windows globally to ensure all readers can access it
try:
    import pytesseract
    default_tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = default_tesseract_path
except ImportError:
    pass



def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a logger with a console handler and a date-wise file handler.
    
    Args:
        name: Name of the logger.
        
    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(Config.LOG_LEVEL)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Date-wise File Handler
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = Config.LOGS_DIR / f"reader_{today_str}.log"
    
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file at {log_file}: {e}", file=sys.stderr)

    return logger


def preprocess_image_for_ocr(pil_img):
    """
    Applies image pre-processing before OCR to improve accuracy:
    1. Upscales images under 150 DPI equivalent resolution.
    2. Converts to grayscale.
    3. Applies adaptive thresholding / binarization.
    
    Args:
        pil_img: A PIL.Image instance.
        
    Returns:
        A pre-processed PIL.Image instance.
    """
    from PIL import Image
    try:
        import cv2
        import numpy as np
    except ImportError:
        cv2 = None

    # 1. Check DPI / resolution and upscale if under 150 DPI equivalent
    dpi = pil_img.info.get("dpi")
    dpi_val = 72.0
    if dpi and isinstance(dpi, (tuple, list)) and len(dpi) >= 2 and dpi[0] > 0:
        dpi_val = float(dpi[0])

    if dpi_val < 150.0:
        scale = 150.0 / dpi_val
        scale = max(1.0, min(scale, 4.0))
        if scale > 1.0:
            new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
            pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

    # 2. Grayscale & Adaptive Thresholding
    if cv2 is not None:
        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")
        np_img = np.array(pil_img)

        if len(np_img.shape) == 3:
            if np_img.shape[2] == 4:
                gray = cv2.cvtColor(np_img, cv2.COLOR_RGBA2GRAY)
            else:
                gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
        else:
            gray = np_img

        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        return Image.fromarray(thresh)
    else:
        # Fallback using PIL
        return pil_img.convert("L")

