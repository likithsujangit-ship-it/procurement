"""
PDF Content Extraction Module.
Reads text content from PDF files using pypdf, with embedded image OCR and full OCR fallback.
"""

import io
from pathlib import Path
from pypdf import PdfReader
from tools.utils import setup_logger, preprocess_image_for_ocr

logger = setup_logger("pdf_reader")


def clean_ocr_text(text: str) -> str:
    """Corrects common OCR misreads in APGENCO procurement PDFs."""
    if not text:
        return text
    import re
    # Fix Room 309 misreads (S09, 509, 809)
    text = re.sub(r'ROOM\s*NO\.?\s*[S58]09', 'Room No.309', text, flags=re.IGNORECASE)
    # Fix Dr MVR RTPP misreads (NTTPS RPP, DRIMLV RTPP)
    text = re.sub(r'Dr\.?\s*NTTPS?\s*RPP', 'Dr. MVR RTPP', text, flags=re.IGNORECASE)
    text = re.sub(r'DRIMLV\s*RTPP', 'Dr. MVR RTPP', text, flags=re.IGNORECASE)
    return text


def extract_pdf_text(filepath: Path) -> str:
    """
    Extracts all text content from a PDF file.
    Extracts native text page by page and OCRs embedded images using PyMuPDF and pytesseract.
    Falls back to local Tesseract OCR if the PDF is an image/scanned.
    
    Args:
        filepath: Path to the PDF file on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting text from PDF: {filepath.name}")
    
    native_chars = 0
    ocr_chars = 0
    
    try:
        reader = PdfReader(filepath)
        text_parts = []
        
        # Open fitz document to extract embedded images if available
        fitz_doc = None
        try:
            import fitz
            fitz_doc = fitz.open(filepath)
        except Exception as fe:
            logger.debug(f"PyMuPDF (fitz) not available or failed to open {filepath.name}: {fe}")

        try:
            import pytesseract
            from PIL import Image
            has_ocr = True
        except ImportError:
            has_ocr = False

        for i, page in enumerate(reader.pages):
            page_content_parts = []
            page_text = page.extract_text() or ""
            if page_text.strip():
                native_chars += len(page_text.strip())
                page_content_parts.append(page_text.strip())

            # OCR embedded images on this page
            has_embedded_images = False
            if fitz_doc and has_ocr and i < len(fitz_doc):
                fitz_page = fitz_doc[i]
                image_list = fitz_page.get_images(full=True)
                if image_list:
                    has_embedded_images = True
                    for img_info in image_list:
                        xref = img_info[0]
                        try:
                            base_image = fitz_doc.extract_image(xref)
                            image_bytes = base_image.get("image")
                            if image_bytes:
                                pil_img = Image.open(io.BytesIO(image_bytes))
                                processed_img = preprocess_image_for_ocr(pil_img)
                                ocr_text = pytesseract.image_to_string(processed_img).strip()
                                if ocr_text:
                                    ocr_chars += len(ocr_text)
                                    page_content_parts.append(f"[OCR from embedded image]: {ocr_text}")
                        except Exception as img_err:
                            logger.debug(f"Failed to process embedded image xref {xref} on page {i + 1}: {img_err}")

            # Intelligent Page-Level OCR Fallback:
            # If the page yields NO native text AND NO successful OCR from embedded images,
            # render the page as a high-DPI image dynamically and run OCR on it.
            if not page_content_parts and fitz_doc and has_ocr and i < len(fitz_doc):
                logger.info(f"Page {i + 1} yielded no native text or embedded images. Rendering page to image for OCR fallback...")
                try:
                    fitz_page = fitz_doc[i]
                    pix = fitz_page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    processed_img = preprocess_image_for_ocr(img)
                    ocr_text = pytesseract.image_to_string(processed_img).strip()
                    if ocr_text:
                        ocr_chars += len(ocr_text)
                        page_content_parts.append(ocr_text)
                except Exception as page_ocr_err:
                    logger.warning(f"Page-level OCR fallback failed on page {i + 1}: {page_ocr_err}")

            if page_content_parts:
                text_parts.append(f"--- Page {i + 1} ---\n" + "\n\n".join(page_content_parts))

        if fitz_doc:
            fitz_doc.close()

        logger.debug(f"PDF Extraction Audit for {filepath.name}: native_chars={native_chars}, ocr_chars={ocr_chars}")

        if not text_parts:
            logger.warning(f"No text extracted from PDF: {filepath.name} (possibly scanned image). Triggering OCR fallback...")
            return clean_ocr_text(extract_pdf_ocr(filepath))
            
        final_text = clean_ocr_text("\n\n".join(text_parts))
        meta_block = f"\n\n__PDF_META__|pages_detected:{len(reader.pages)}|pages_processed:{len(text_parts)}|ocr_pages:{ocr_chars > 0}"
        return final_text + meta_block

    except Exception as e:
        logger.error(f"Error reading PDF {filepath.name}: {e}")
        return f"[Error reading PDF file: {e}]"


def extract_pdf_ocr(filepath: Path) -> str:
    """Uses PyMuPDF (fitz) and pytesseract to OCR a scanned PDF with image preprocessing."""
    try:
        import fitz
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.error("PyMuPDF (fitz) or pytesseract is not installed. Cannot perform OCR fallback.")
        return "[PDF Empty or Scanned Image - No readable text found]"
        
    try:
        logger.info(f"Converting PDF {filepath.name} to images for OCR...")
        doc = fitz.open(filepath)
        ocr_text_parts = []
        ocr_chars = 0
        
        for i in range(len(doc)):
            logger.info(f"OCRing page {i + 1} of {len(doc)}...")
            page = doc.load_page(i)
            # Render page to an image (scale up for better OCR, 300 DPI approx)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            # Convert fitz pixmap to PIL Image for pytesseract
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            processed_img = preprocess_image_for_ocr(img)
            
            page_text = pytesseract.image_to_string(processed_img).strip()
            if page_text:
                ocr_chars += len(page_text)
                ocr_text_parts.append(f"--- Page {i + 1} (OCR) ---\n{page_text}")
                
        doc.close()
        logger.debug(f"PDF Extraction Audit (Full OCR Fallback) for {filepath.name}: native_chars=0, ocr_chars={ocr_chars}")
            
        if not ocr_text_parts:
            return "[PDF Empty or Scanned Image - OCR produced no text]"
            
        final_text = "\n\n".join(ocr_text_parts)
        meta_block = f"\n\n__PDF_META__|pages_detected:{len(doc)}|pages_processed:{len(ocr_text_parts)}|ocr_pages:True"
        return final_text + meta_block
    except Exception as e:
        logger.error(f"OCR fallback failed for {filepath.name}: {e}")
        return f"[OCR Fallback failed: Please ensure Tesseract is installed on your OS. Error: {e}]"
