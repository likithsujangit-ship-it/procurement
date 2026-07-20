"""
PowerPoint (PPTX/PPT) Content Extraction Module.
Reads slides, text shapes, and notes using python-pptx.
"""

from pathlib import Path
from pptx import Presentation
from tools.utils import setup_logger

logger = setup_logger("ppt_reader")


def extract_ppt_text(filepath: Path) -> str:
    """
    Extracts text from slides in a .pptx file.
    Provides troubleshooting fallback for older .ppt files.
    
    Args:
        filepath: Path to the PowerPoint document on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from PPTX: {filepath.name}")
    
    # Handle older .ppt files gracefully
    if filepath.suffix.lower() == ".ppt":
        logger.warning(f"File {filepath.name} is a legacy .ppt file. python-pptx only supports .pptx.")
        return (
            "[Unsupported Format: Legacy .ppt file]\n"
            "Troubleshooting: Please convert this file to the modern .pptx format "
            "using Microsoft PowerPoint or LibreOffice to allow automated content reading."
        )

    try:
        prs = Presentation(filepath)
        text_parts = []
        
        for slide_idx, slide in enumerate(prs.slides):
            text_parts.append(f"--- Slide {slide_idx + 1} ---")
            
            # Extract text from shapes
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())
                    
            if slide_text:
                text_parts.append("\n".join(slide_text))
            else:
                text_parts.append("[No text on slide]")
                
        if not text_parts:
            return "[PowerPoint presentation has no slides]"
            
        return "\n\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error reading PPTX {filepath.name}: {e}")
        return f"[Error reading PPTX file: {e}]"
