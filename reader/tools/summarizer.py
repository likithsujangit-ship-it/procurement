"""
Email Summarizer Module.
Uses the Groq API (Llama 3.3 70B) to synthesize emails and their attachment
contents into structured reports with action items, tasks, and priorities.
"""

import json
from typing import Dict, Any, List
from tools.utils import setup_logger
from tools.groq_client import GroqClient

logger = setup_logger("summarizer")


def summarize_email(
    email_data: Dict[str, Any],
    extracted_resources: Dict[str, List[str]],
    attachment_contents: Dict[str, str]
) -> Dict[str, Any]:
    """
    Summarizes an email and its attachments using Groq Llama 3.3 70B.
    Fills in priority, pending tasks, meeting dates, and action items.
    
    Args:
        email_data: Dictionary containing sender, subject, date, body.
        extracted_resources: Pattern-extracted links, phones, emails, etc.
        attachment_contents: Dictionary mapping filenames to extracted text.
        
    Returns:
        Structured dictionary containing summary report.
    """
    logger.info(f"Summarizing email ID {email_data['id']} using Groq client.")
    groq = GroqClient()
    
    # 1. If Groq is available, call it to create an intelligent summary
    if groq.is_available():
        try:
            return _summarize_with_groq(groq, email_data, extracted_resources, attachment_contents)
        except Exception as e:
            logger.error(f"Groq summarization failed: {e}. Falling back to rule-based summary.")
            
    return _summarize_with_rules(email_data, extracted_resources, attachment_contents)


def _summarize_with_groq(
    groq: GroqClient,
    email_data: Dict[str, Any],
    resources: Dict[str, List[str]],
    attachments: Dict[str, str]
) -> Dict[str, Any]:
    """Summarizes email content using Groq Llama 3.3 70B model in JSON format."""
    
    system_prompt = (
        "You are an elite executive assistant and AI analyst. "
        "Your task is to analyze an email along with its attachments, extract structured information, "
        "and generate a comprehensive summary. You must respond ONLY with a valid JSON object. "
        "Do not include any conversational filler, markdown formatting (like ```json), or explanations.\n\n"
        "The JSON object must contain the following keys exactly:\n"
        "- 'sender': string (From header)\n"
        "- 'subject': string (Subject header)\n"
        "- 'date': string (Date header)\n"
        "- 'priority': string (one of: 'High', 'Medium', 'Low')\n"
        "- 'summary': string (a concise 3-4 sentence paragraph summarizing the core conversation/request)\n"
        "- 'action_items': list of strings (concrete actions the reader needs to take)\n"
        "- 'pending_tasks': list of strings (tasks mentioned as incomplete or waiting for others)\n"
        "- 'meeting_dates': list of strings (any specific meeting dates and times mentioned in the email)\n"
        "- 'important_links': list of strings (links that are key to the email context)\n"
        "- 'resources': dict containing extracted identifiers (OTPs, tracking numbers, invoices, references)\n"
        "- 'attachment_summary': list of dicts (each containing 'filename', 'size_bytes', and 'content_summary')\n"
    )
    
    # Format attachments info for LLM prompt
    attachment_descriptions = []
    for att in email_data.get("attachments", []):
        name = att["filename"]
        size = att["size"]
        text_preview = attachments.get(name, "")[:2000] # Limit size to prevent token blowup
        attachment_descriptions.append(
            f"Filename: {name}\nSize: {size} bytes\nExtracted Content:\n{text_preview}\n---"
        )
        
    user_prompt = (
        f"EMAIL DETAILS:\n"
        f"From: {email_data['sender']}\n"
        f"Subject: {email_data['subject']}\n"
        f"Date: {email_data['date']}\n"
        f"Body Text:\n{email_data['body']}\n\n"
        f"REGEX-EXTRACTED RESOURCES:\n{json.dumps(resources, indent=2)}\n\n"
        f"ATTACHMENTS CONTENT:\n" + "\n".join(attachment_descriptions)
    )
    
    raw_response = groq.get_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_json=True
    )
    
    logger.debug(f"Raw response from Groq summarizer: {raw_response}")
    return json.loads(raw_response)


def _summarize_with_rules(
    email_data: Dict[str, Any],
    resources: Dict[str, List[str]],
    attachments: Dict[str, str]
) -> Dict[str, Any]:
    """Rule-based fallback summary when Groq API is unavailable."""
    logger.debug("Generating summary using rule-based fallback.")
    
    # 1. Simple Priority Heuristic
    priority = "Low"
    high_priority_keywords = ["urgent", "asap", "important", "alert", "action required", "deadline", "otp", "invoice"]
    body_lower = email_data["body"].lower()
    subject_lower = email_data["subject"].lower()
    if any(kw in body_lower or kw in subject_lower for kw in high_priority_keywords):
        priority = "High"
    elif any(kw in body_lower or kw in subject_lower for kw in ["meeting", "schedule", "please", "review"]):
        priority = "Medium"
        
    # 2. Basic Text Truncation for Summary
    body_clean = email_data["body"].strip()
    summary_text = body_clean[:200] + "..." if len(body_clean) > 200 else body_clean
    if not summary_text:
        summary_text = "[No Plain Text Content in Email]"

    # 3. Formulate important links
    all_links = (
        resources.get("google_drive_links", []) +
        resources.get("onedrive_links", []) +
        resources.get("github_links", []) +
        resources.get("general_urls", [])
    )
    
    # 4. Formulate attachments metadata summary
    att_summaries = []
    for att in email_data.get("attachments", []):
        filename = att["filename"]
        content = attachments.get(filename, "")
        preview = content[:150] + "..." if len(content) > 150 else content
        if not preview or preview.isspace():
            preview = "[No readable text content extracted]"
        att_summaries.append({
            "filename": filename,
            "size_bytes": att["size"],
            "content_summary": preview
        })

    return {
        "sender": email_data["sender"],
        "subject": email_data["subject"],
        "date": email_data["date"],
        "priority": priority,
        "summary": f"Fallback Rule-Based Summary: {summary_text}",
        "action_items": ["Please review the email contents manually (API Offline)."],
        "pending_tasks": ["Follow up on any requests made in this mail."],
        "meeting_dates": [],
        "important_links": all_links,
        "resources": {
            "otps": resources.get("otps", []),
            "tracking_numbers": resources.get("tracking_numbers", []),
            "invoices": resources.get("invoices", []),
            "reference_numbers": resources.get("reference_numbers", [])
        },
        "attachment_summary": att_summaries
    }
