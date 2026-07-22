from pathlib import Path
from tools.utils import setup_logger
import email
from email import policy

logger = setup_logger("email_reader")


def extract_email_text(filepath: Path) -> str:
    """
    Extracts text content from email files (.eml, .msg).
    
    Args:
        filepath: Path to the email file on disk.
        
    Returns:
        Extracted text content as a string.
    """
    logger.info(f"Extracting email text from: {filepath.name}")
    
    suffix = filepath.suffix.lower()
    text_parts = []
    
    try:
        if suffix == ".eml":
            with open(filepath, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
                
            text_parts.append(f"Subject: {msg.get('subject', '')}")
            text_parts.append(f"From: {msg.get('from', '')}")
            text_parts.append(f"To: {msg.get('to', '')}")
            text_parts.append(f"Date: {msg.get('date', '')}")
            text_parts.append("-" * 40)
            
            body = msg.get_body(preferencelist=('plain', 'html'))
            if body:
                text_parts.append(body.get_content())
                
        elif suffix == ".msg":
            import extract_msg
            msg = extract_msg.Message(str(filepath))
            
            text_parts.append(f"Subject: {msg.subject}")
            text_parts.append(f"From: {msg.sender}")
            text_parts.append(f"To: {msg.to}")
            text_parts.append(f"Date: {msg.date}")
            text_parts.append("-" * 40)
            
            if msg.body:
                text_parts.append(msg.body)
            msg.close()
            
        else:
            return f"[Unsupported email format: {suffix}]"
            
        return "\n".join(text_parts).strip()
        
    except Exception as e:
        logger.error(f"Error reading email file {filepath.name}: {e}")
        return f"[Error reading email file: {e}]"
