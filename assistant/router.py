"""
Router Module for UNIFIED ASSISTANT.
Classifies user instructions into distinct actions (e.g., Send, Read, Summarize) 
using Groq LLM (llama-3.3-70b-versatile) or regex mapping.
"""

import json
import re
from typing import Dict, Any, Optional
from groq import Groq

from assistant.config import READER_CONFIG, SENDER_CONFIG, import_reader_module

utils_mod = import_reader_module("tools.utils")
setup_logger = utils_mod.setup_logger
logger = setup_logger("assistant_router")


def route_instruction(instruction: str) -> Dict[str, Any]:
    """
    Classifies a natural language query and extracts routing parameters.
    Uses Groq API with a regex fallback.
    """
    logger.info(f"Routing instruction: '{instruction}'")
    inst_lower = instruction.lower()
    if "give all summaries" in inst_lower:
        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        found_emails = re.findall(email_pattern, instruction)
        return {
            "action": "TEST_ALL_SUMMARIES",
            "parameters": {
                "sender": found_emails[0] if found_emails else None,
                "query_context": instruction
            }
        }

    api_key = READER_CONFIG.GROQ_API_KEY or SENDER_CONFIG.GROQ_API_KEY
    if api_key and api_key != "gsk_your_groq_api_key_here":
        try:
            return _route_with_groq(instruction, api_key)
        except Exception as e:
            logger.error(f"Groq routing failed: {e}. Falling back to regex routing.")

    return _route_with_regex(instruction)


def _route_with_groq(instruction: str, api_key: str) -> Dict[str, Any]:
    """Classifies query using Groq Llama 3.3 70B."""
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
        "7. 'SEARCH_DOCUMENTS': User wants to search for, locate, find, or query files/documents/invoices/resumes using semantic natural language.\n"
        "8. 'INTELLIGENT_EXTRACT': User wants to perform intelligent extraction on an email to get structured JSON data for commercial/logistics/rfq intents.\n\n"
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
    result = json.loads(raw_content)

    inst_lower = instruction.lower()
    if "extract" in inst_lower:
        file_match = re.search(r'\b([\w-]+\.(?:pdf|docx|doc|xlsx|xls|csv|png|jpeg|zip))\b', instruction, re.IGNORECASE)
        if not file_match or any(k in inst_lower for k in ["from", "mail", "email", "latest", "inbox"]):
            result["action"] = "INTELLIGENT_EXTRACT"

    return result


def _route_with_regex(instruction: str) -> Dict[str, Any]:
    """Fallback router using keywords."""
    logger.debug("Running regex fallback routing.")
    inst_lower = instruction.lower()
    
    found_types = []
    for ext in ["pdf", "docx", "doc", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "zip"]:
        if f".{ext}" in inst_lower or f" {ext} " in inst_lower or inst_lower.endswith(f" {ext}"):
            found_types.append(ext)
            
    file_type = found_types[0] if found_types else None
    
    file_match = re.search(r'\b([\w-]+\.(?:pdf|docx|doc|xlsx|xls|csv|png|jpeg|zip))\b', instruction, re.IGNORECASE)
    filename = file_match.group(1) if file_match else None
    
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    found_emails = re.findall(email_pattern, instruction)
    target_email = found_emails[0] if found_emails else None

    if "send" in inst_lower or "mail to" in inst_lower or "write to" in inst_lower:
        action = "SEND_EMAIL"
    elif "extract" in inst_lower:
        if filename and not any(k in inst_lower for k in ["from", "mail", "email", "latest", "inbox"]):
            action = "EXTRACT_FILE"
        else:
            action = "INTELLIGENT_EXTRACT"
    elif "summarize" in inst_lower or "summary" in inst_lower:
        if filename:
            action = "SUMMARIZE_FILE"
        else:
            action = "SUMMARIZE_EMAIL"
    elif "download" in inst_lower or "fetch attachments" in inst_lower:
        action = "DOWNLOAD_ATTACHMENTS"
    elif "search" in inst_lower or "find" in inst_lower or "locate" in inst_lower:
        action = "SEARCH_DOCUMENTS"
    elif "read" in inst_lower or "fetch" in inst_lower or "list" in inst_lower:
        action = "READ_EMAIL"
    else:
        action = "INTELLIGENT_EXTRACT" if ("extract" in inst_lower or "po" in inst_lower or "rfq" in inst_lower) else "READ_EMAIL"

    return {
        "action": action,
        "parameters": {
            "recipient": target_email,
            "sender": target_email,
            "filename": filename,
            "file_type": file_type,
            "query_context": instruction
        }
    }
