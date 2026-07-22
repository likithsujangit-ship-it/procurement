"""
Command Parser Module for EMAIL SENDER.
Extracts email details (recipients, attachments, subject, body, tone) 
from natural language using Groq LLM (llama-3.3-70b-versatile) with a regex fallback.
"""

import json
import re
from typing import Dict, Any, List, Optional
from groq import Groq
from config import Config
from tools.utils import setup_logger
from tools.contacts import resolve_contact

logger = setup_logger("parser")


def parse_natural_language_command(command: str) -> Dict[str, Any]:
    """
    Parses a natural language instruction to extract email metadata.
    Uses Groq API for structural extraction, with fallback to basic regex.
    """
    logger.info(f"Parsing natural language instruction: '{command}'")
    
    if Config.GROQ_API_KEY and Config.GROQ_API_KEY != "gsk_your_groq_api_key_here":
        try:
            return _parse_with_groq(command)
        except Exception as e:
            logger.error(f"Groq parsing failed: {e}. Falling back to regex parser.")

    return _parse_with_regex(command)


def _parse_with_groq(command: str) -> Dict[str, Any]:
    """Uses Groq and Llama-3.3-70b-versatile to extract email data structure."""
    client = Groq(api_key=Config.GROQ_API_KEY)
    
    system_prompt = (
        "You are an expert NLP parser for an AI Email Assistant. "
        "Your task is to parse the user's natural language request and extract details needed to send an email. "
        "Respond ONLY with a valid JSON object. Do not include any conversational filler, markdown formatting (like ```json), or explanations.\n\n"
        "The JSON object must contain the following keys exactly:\n"
        "- 'recipients': list of strings (resolved email addresses or names like 'hr', 'manager')\n"
        "- 'cc': list of strings (CC recipients)\n"
        "- 'bcc': list of strings (BCC recipients)\n"
        "- 'subject_hint': string (any mention of subject or context, or empty string)\n"
        "- 'body_hint': string (any mention of what to say, or empty string)\n"
        "- 'tone': string (one of: 'professional', 'casual', 'formal', 'follow-up', 'thank-you', 'meeting-request', 'leave-request', 'internship-request', 'complaint', 'support', 'application', 'reminder', or 'default')\n"
        "- 'attachments': list of strings (filenames mentioned like 'resume.pdf', 'marks.pdf')\n"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": command}
        ],
        temperature=0.0,
        response_format={"type": "json_object"}
    )

    raw_content = response.choices[0].message.content.strip()
    logger.debug(f"Raw response from Groq parser: {raw_content}")
    data = json.loads(raw_content)

    data["recipients"] = [resolve_contact(r) for r in data.get("recipients", [])]
    data["cc"] = [resolve_contact(c) for c in data.get("cc", [])]
    data["bcc"] = [resolve_contact(b) for b in data.get("bcc", [])]
    return data


def _parse_with_regex(command: str) -> Dict[str, Any]:
    """Fallback parser using regex patterns if API is unavailable."""
    logger.debug("Running regex fallback parser.")
    
    # 1. Extract email addresses
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    found_emails = re.findall(email_pattern, command)
    
    # 2. Extract potential contact aliases (hr, boss, manager, team)
    words = command.lower().split()
    alias_matches = []
    for w in words:
        resolved = resolve_contact(w)
        if resolved != w and "@" in resolved and resolved not in found_emails:
            alias_matches.append(resolved)
            
    recipients = list(dict.fromkeys(found_emails + alias_matches))
    
    # 3. Extract attachment filenames
    file_pattern = r'\b[a-zA-Z0-9_\-]+\.(?:pdf|docx?|xlsx?|png|jpg|txt)\b'
    attachments = re.findall(file_pattern, command, re.IGNORECASE)
    
    # 4. Infer tone from context keywords
    cmd_lower = command.lower()
    tone = "default"
    if "internship" in cmd_lower:
        tone = "internship-request"
    elif "leave" in cmd_lower or "vacation" in cmd_lower:
        tone = "leave-request"
    elif "meeting" in cmd_lower or "schedule" in cmd_lower:
        tone = "meeting-request"
    elif "complaint" in cmd_lower or "issue" in cmd_lower:
        tone = "complaint"
    elif "formal" in cmd_lower:
        tone = "formal"
    elif "casual" in cmd_lower:
        tone = "casual"

    # 5. Extract subject hint
    subject_match = re.search(r'regarding\s+([^.\n]+)', command, re.IGNORECASE)
    subject_hint = subject_match.group(1).strip() if subject_match else ""
    if not subject_hint:
        sub_about = re.search(r'about\s+([^.\n]+)', command, re.IGNORECASE)
        subject_hint = sub_about.group(1).strip() if sub_about else ""

    # 6. Extract body hint
    body_match = re.search(r'saying\s+([^.\n]+)', command, re.IGNORECASE)
    body_hint = body_match.group(1).strip() if body_match else command

    return {
        "recipients": recipients,
        "cc": [],
        "bcc": [],
        "subject_hint": subject_hint,
        "body_hint": body_hint,
        "tone": tone,
        "attachments": attachments
    }
