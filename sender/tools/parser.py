"""
Command Parser Module for EMAIL SENDER.
Extracts email details (recipients, attachments, subject, body, tone) 
from natural language using the Groq Llama 3.3 70B model with a regex fallback.
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
    
    Args:
        command: The natural language prompt from the user.
        
    Returns:
        A dictionary with extracted email details.
    """
    logger.info(f"Parsing natural language instruction: '{command}'")
    
    # Try using Groq if key is set and valid
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
        "- 'attachments': list of strings (filenames mentioned like 'resume.pdf', 'marks.pdf')\n\n"
        "Example input: 'Send resume.pdf and marks.pdf to hr@gmail.com regarding internship saying I want to apply.'\n"
        "Example output:\n"
        "{\n"
        "  \"recipients\": [\"hr@gmail.com\"],\n"
        "  \"cc\": [],\n"
        "  \"bcc\": [],\n"
        "  \"subject_hint\": \"internship\",\n"
        "  \"body_hint\": \"I want to apply\",\n"
        "  \"tone\": \"internship-request\",\n"
        "  \"attachments\": [\"resume.pdf\", \"marks.pdf\"]\n"
        "}"
    )
    
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
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
    
    # Resolve names like 'hr' using the contacts module
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
    
    # Check for known contact keywords
    keywords = ["hr", "manager", "admin", "support", "billing"]
    recipients = list(found_emails)
    for kw in keywords:
        if re.search(r'\b' + kw + r'\b', command, re.IGNORECASE):
            recipients.append(resolve_contact(kw))
            
    # Remove duplicates
    recipients = list(dict.fromkeys(recipients))
    
    # 2. Extract attachments (e.g. filename.ext)
    file_pattern = r'\b[\w-]+\.(?:pdf|docx|doc|ppt|pptx|zip|rar|png|jpeg|jpg|xlsx|xls|csv|txt)\b'
    attachments = re.findall(file_pattern, command, re.IGNORECASE)
    attachments = list(dict.fromkeys(attachments))
    
    # 3. Detect tone
    tone = "default"
    tone_mappings = {
        "professional": ["professional", "work"],
        "casual": ["casual", "friendly", "informal"],
        "formal": ["formal", "official"],
        "follow-up": ["follow-up", "followup"],
        "thank-you": ["thank you", "thanks", "gratitude"],
        "meeting-request": ["meeting", "schedule", "appointment"],
        "leave-request": ["leave", "sick", "vacation"],
        "internship-request": ["internship", "intern"],
        "complaint": ["complaint", "issue", "complain"],
        "support": ["support", "help"],
        "application": ["apply", "application", "resume", "job"],
        "reminder": ["remind", "reminder"]
    }
    
    lower_command = command.lower()
    for t_name, words in tone_mappings.items():
        if any(w in lower_command for w in words):
            tone = t_name
            break
            
    # 4. Rough subject and body hint extraction
    subject_hint = ""
    body_hint = ""
    
    # Check for "regarding..." or "about..."
    about_match = re.search(r'\b(?:regarding|about|subject)\s+([^.]+)', command, re.IGNORECASE)
    if about_match:
        subject_hint = about_match.group(1).strip()
        
    # Check for "saying..."
    saying_match = re.search(r'\b(?:saying|message|content)\s+([^.]+)', command, re.IGNORECASE)
    if saying_match:
        body_hint = saying_match.group(1).strip()
        
    return {
        "recipients": recipients,
        "cc": [],
        "bcc": [],
        "subject_hint": subject_hint,
        "body_hint": body_hint or command,
        "tone": tone,
        "attachments": attachments
    }
