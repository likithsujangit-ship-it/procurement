import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def truncate_text(text: str, max_tokens: int = 40000) -> str:
    """
    Very basic character-based truncation approximation.
    Assuming ~4 chars per token.
    If text exceeds max, keep the beginning and the end.
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
        
    logger.warning("Context too large, truncating middle portion.")
    half = max_chars // 2
    return text[:half] + "\n\n...[TRUNCATED]...\n\n" + text[-half:]

def merge_context(email_metadata: Dict[str, Any], email_body: str, attachments: List[Dict[str, str]]) -> str:
    """
    Combines email and attachments into a unified markdown string for the LLM.
    """
    lines = []
    lines.append("=== EMAIL METADATA ===")
    for k, v in email_metadata.items():
        lines.append(f"{k}: {v}")
    
    lines.append("\n=== EMAIL BODY ===")
    lines.append(email_body)
    
    for att in attachments:
        lines.append(f"\n=== ATTACHMENT: {att.get('filename', 'Unknown')} ===")
        lines.append(att.get('raw_text', ''))
        
    unified_text = "\n".join(lines)
    return truncate_text(unified_text)
