import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def truncate_text(text: str, max_tokens: int = 4000) -> str:
    """
    Character-based truncation approximation ensuring total prompt fits well within Groq TPM limits.
    Assuming ~4 chars per token.
    If text exceeds max, keep the beginning and the end.
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
        
    logger.warning(f"Context size ({len(text)} chars) exceeds safe LLM limit ({max_chars} chars), truncating middle portion.")
    half = max_chars // 2
    return text[:half] + "\n\n...[TRUNCATED MIDDLE CONTEXT]...\n\n" + text[-half:]

def merge_context(email_metadata: Dict[str, Any], email_body: str, attachments: List[Dict[str, str]]) -> str:
    """
    Combines email and attachments into a unified markdown string for the LLM.
    Slices each attachment intelligently so that ALL attachments contribute to context
    without exceeding Groq rate limits or truncating intermediate files.
    """
    lines = []
    lines.append("=== EMAIL METADATA ===")
    for k, v in email_metadata.items():
        lines.append(f"{k}: {v}")
    
    lines.append("\n=== EMAIL BODY ===")
    lines.append(email_body[:2000] if email_body else "")
    
    num_att = len(attachments)
    max_per_att = 2500 if num_att <= 3 else max(1200, 8000 // max(1, num_att))
    
    for att in attachments:
        filename = att.get("filename", "Unknown")
        raw_text = (att.get("raw_text") or "").strip()
        lines.append(f"\n=== ATTACHMENT: {filename} ===")
        if len(raw_text) > max_per_att:
            half = max_per_att // 2
            att_summary = raw_text[:half] + "\n...[TRUNCATED FILE CONTENT]...\n" + raw_text[-half:]
            lines.append(att_summary)
        else:
            lines.append(raw_text if raw_text else "[No text content extracted]")
            
    unified_text = "\n".join(lines)
    return truncate_text(unified_text, max_tokens=3500)
