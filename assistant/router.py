"""
Router Module for UNIFIED ASSISTANT.
Classifies user instructions into distinct actions (e.g., Send, Read, Summarize) 
using Groq LLM (Llama 3.3 70B) or regex mapping.
"""

import json
import re
from typing import Dict, Any, Optional
from groq import Groq
from assistant.config import READER_CONFIG, SENDER_CONFIG, import_reader_module

# Safe dynamic import of logging setup
utils_mod = import_reader_module("tools.utils")
setup_logger = utils_mod.setup_logger
logger = setup_logger("assistant_router")


def route_instruction(instruction: str) -> Dict[str, Any]:
    """
    Classifies a natural language query and extracts routing parameters.
    Uses Groq LLM with a regex fallback.
    
    Args:
        instruction: Natural language string.
        
    Returns:
        Dict containing 'action' and 'parameters'.
    """
    logger.info(f"Routing instruction: '{instruction}'")
    
    # Try using Groq via Reader Config API Key (shared key setup)
    api_key = READER_CONFIG.GROQ_API_KEY or SENDER_CONFIG.GROQ_API_KEY
    if api_key and api_key != "gsk_your_groq_api_key_here":
        try:
            return _route_with_groq(instruction, api_key)
        except Exception as e:
            logger.error(f"Groq routing failed: {e}. Falling back to regex routing.")
            
    return _route_with_regex(instruction)


def _route_with_groq(instruction: str, api_key: str) -> Dict[str, Any]:
    """Classifies query using Llama 3.3 70B."""
    client = Groq(api_key=api_key)
    
    system_prompt = (
        "You are the central command router for EMAIL_AI (an email and document assistant).\n"
        "Your task is to classify the user's instruction into one of the following actions:\n"
        "1. 'SEND_EMAIL': User wants to draft/send an email.\n"
        "2. 'READ_EMAIL': User wants to fetch, read, or list emails.\n"
        "3. 'SUMMARIZE_EMAIL': User wants to fetch and summarize email content.\n"
        "4. 'DOWNLOAD_ATTACHMENTS': User wants to download files/attachments from emails.\n"
        "5. 'EXTRACT_FILE': User wants to extract text/data from files (PDF, Word, Excel, CSV, ZIP, Image OCR).\n"
        "6. 'SUMMARIZE_FILE': User wants to summarize a file or set of files.\n"
        "7. 'SEARCH_DOCUMENTS': User wants to search for, locate, find, or query files/documents/invoices/resumes using semantic natural language.\n\n"
        "Respond ONLY with a JSON object. No conversational text, no markdown block (e.g. ```json).\n"
        "The JSON object must have:\n"
        "- 'action': The selected action string (all caps, matching the list above).\n"
        "- 'parameters': A dictionary containing parsed variables, e.g.:\n"
        "  - 'recipient': string (email address or contact name if sending)\n"
        "  - 'sender': string (email or contact name filtering for reading/summarizing)\n"
        "  - 'filename': string (specific filename like 'resume.pdf' if extracting/summarizing)\n"
        "  - 'file_type': string (extension like 'pdf', 'docx', 'xlsx' if general action)\n"
        "  - 'query_context': string (brief summary of what they want to do)\n"
    )
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction}
        ],
        temperature=0.0,
        response_format={"type": "json_object"}
    )
    
    raw_content = response.choices[0].message.content.strip()
    logger.debug(f"Router response: {raw_content}")
    
    return json.loads(raw_content)


def _route_with_regex(instruction: str) -> Dict[str, Any]:
    """Fallback router using keywords."""
    logger.debug("Running regex fallback routing.")
    inst_lower = instruction.lower()
    
    # Detect file type filters (supporting multiple extensions)
    found_types = []
    extensions = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "csv", "zip", "txt", "png", "jpeg", "jpg", "html"]
    for ext in extensions:
        if f".{ext}" in inst_lower or f" {ext}s" in inst_lower or f" {ext}" in inst_lower or inst_lower == ext or inst_lower == f".{ext}":
            found_types.append(ext)
            
    action = "READ_EMAIL"
    parameters: Dict[str, Any] = {
        "recipient": None,
        "sender": None,
        "filename": None,
        "file_type": ", ".join(found_types) if found_types else None,
        "query_context": instruction
    }

    # 1. Detect SEARCH_DOCUMENTS (highest priority for "find", "search", "show invoice", etc.)
    if any(k in inst_lower for k in ["find", "search", "show invoice", "show resume", "show document", "show file", "where is"]):
        if not any(k in inst_lower for k in ["download", "save attachment"]):
            action = "SEARCH_DOCUMENTS"

    # 2. Detect SEND_EMAIL
    elif any(k in inst_lower for k in ["send", "write", "draft", "mail to", "email to"]):
        action = "SEND_EMAIL"
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+', instruction)
        if email_match:
            parameters["recipient"] = email_match.group(0)

    # 3. Detect SUMMARIZE_EMAIL vs SUMMARIZE_FILE
    elif "summarize" in inst_lower or "summary" in inst_lower:
        if any(k in inst_lower for k in ["file", "pdf", "docx", "xlsx", "invoice", "resume", "document"]):
            action = "SUMMARIZE_FILE"
            # Attempt to extract filename
            file_match = re.search(r'\b([\w-]+\.(?:pdf|docx|doc|xlsx|xls|csv|png|jpeg|zip))\b', instruction, re.IGNORECASE)
            if file_match:
                parameters["filename"] = file_match.group(1)
        else:
            action = "SUMMARIZE_EMAIL"
            
    # 4. Detect DOWNLOAD_ATTACHMENTS
    elif any(k in inst_lower for k in ["download", "save attachment", "get attachment"]):
        action = "DOWNLOAD_ATTACHMENTS"

    # 5. Detect EXTRACT_FILE
    elif any(k in inst_lower for k in ["extract", "read pdf", "read excel", "read docx", "ocr"]):
        action = "EXTRACT_FILE"
        file_match = re.search(r'\b([\w-]+\.(?:pdf|docx|doc|xlsx|xls|csv|png|jpeg|zip))\b', instruction, re.IGNORECASE)
        if file_match:
            parameters["filename"] = file_match.group(1)

    # Extract sender query if applicable
    if "from" in inst_lower:
        from_match = re.search(r'\bfrom\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+|\w+)', instruction, re.IGNORECASE)
        if from_match:
            parameters["sender"] = from_match.group(1)

    return {
        "action": action,
        "parameters": parameters
    }
