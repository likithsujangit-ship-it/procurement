"""
Email Summarizer Module.
Uses the Groq API (Llama 3.3 70B) to synthesize emails and their attachment
contents into structured reports with action items, tasks, and priorities.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
from config import Config
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
        model="llama-3.3-70b-versatile",
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


def save_extraction_outputs(
    email_data: Dict[str, Any],
    summary: Dict[str, Any],
    attachment_contents: Dict[str, str],
    structured_extractions: Dict[str, Any] = None
) -> Tuple[Path, Path]:
    """
    Saves summary.txt and extracted_data.json under:
    reader/outputs/<sender_prefix>/<DD-MM-YYYY-(HH_MM_SS_fff)>/
    and updates root reader/outputs/ summary files.
    """
    # 1. Parse sender email prefix
    sender_raw = email_data.get("sender", "")
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
    email = email_match.group(0) if email_match else sender_raw.strip().lower()
    prefix = email.split("@")[0].strip() if "@" in email else email
    prefix = "".join(c for c in prefix if c.isalnum() or c in ("-", "_", "."))
    if not prefix:
        prefix = "unknown"

    # 2. Parse timestamp folder name matching download format
    internal_date_ms = email_data.get("internalDate")
    if internal_date_ms:
        try:
            dt = datetime.fromtimestamp(int(internal_date_ms) / 1000.0)
        except Exception:
            dt = datetime.now()
    else:
        dt = datetime.now()

    time_folder_name = dt.strftime("%d-%m-%Y-(%H_%M_%S_%f)")[:-3]

    # 3. Create target output directory
    output_dir = Config.OUTPUTS_DIR / prefix / time_folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 4. Formulate summary.txt text
    txt_lines = [
        "=" * 80,
        "                                EMAIL SUMMARY REPORT                            ",
        "=" * 80,
        f"Subject:        {summary.get('subject', 'N/A')}",
        f"From:           {summary.get('sender', 'N/A')}",
        f"Date:           {summary.get('date', 'N/A')}",
        f"Priority:       {summary.get('priority', 'N/A')}",
        "-" * 80,
        "SUMMARY",
        "-" * 80,
        f"{summary.get('summary', 'No summary provided.')}",
        "",
        "-" * 80,
        "ACTION ITEMS",
        "-" * 80,
    ]
    for item in summary.get("action_items", []):
        txt_lines.append(f"  - {item}")

    txt_lines.extend([
        "",
        "-" * 80,
        "PENDING TASKS",
        "-" * 80,
    ])
    for task in summary.get("pending_tasks", []):
        txt_lines.append(f"  - {task}")

    txt_lines.extend([
        "",
        "-" * 80,
        "MEETING DATES & IMPORTANT LINKS",
        "-" * 80,
        f"Meeting Dates:  {', '.join(summary.get('meeting_dates', [])) or 'None'}",
        f"Important Links:{', '.join(summary.get('important_links', [])) or 'None'}",
        "",
        "-" * 80,
        "ATTACHMENTS & EXTRACTIONS",
        "-" * 80,
    ])
    for att in summary.get("attachment_summary", []):
        fn = att.get("filename", "")
        txt_lines.append(f"File: {fn} ({att.get('size_bytes', 0)} bytes)")
        txt_lines.append(f"Snippet: {att.get('content_summary', '')}")
        txt_lines.append("-")

    txt_lines.append("=" * 80)
    summary_txt_content = "\n".join(txt_lines)

    # Write summary.txt with prefix
    txt_path = output_dir / f"{prefix}_summary.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(summary_txt_content)

    # 5. Formulate flat structured JSON payload matching exact master schema
    if not (structured_extractions and isinstance(structured_extractions, dict) and "intent" in structured_extractions and structured_extractions.get("items")):
        try:
            from tools.intelligent_extractor.orchestrator import PipelineOrchestrator
            metadata = {
                "subject": email_data.get("subject", ""),
                "sender": email_data.get("sender", ""),
                "date": email_data.get("date", ""),
                "internal_date_ms": email_data.get("internalDate", "")
            }
            body = email_data.get("body", "") + "\n" + email_data.get("html_body", "")
            
            # Find attachment paths from files directory or temporary workspace
            sender_raw = email_data.get("sender", "unknown")
            m = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
            clean_prefix = re.sub(r'[^a-zA-Z0-9._-]', '', m.group(0).split('@')[0]) if m else "unknown"
            
            att_paths = []
            files_sender_dir = Config.DOWNLOAD_DIR / clean_prefix
            if files_sender_dir.exists():
                time_dirs = sorted(files_sender_dir.glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)
                if time_dirs:
                    att_paths = list(time_dirs[0].glob('*'))
            
            orchestrator = PipelineOrchestrator()
            extracted_res = orchestrator.run(metadata, body, att_paths)
            if extracted_res and isinstance(extracted_res, dict) and "intent" in extracted_res:
                structured_extractions = extracted_res
        except Exception as e:
            logger.warning(f"Automatic pipeline extraction in save_extraction_outputs failed: {e}")

    if structured_extractions and isinstance(structured_extractions, dict) and "intent" in structured_extractions:
        full_json_payload = structured_extractions
    else:
        att_list = []
        for fn, content in attachment_contents.items():
            ext = Path(fn).suffix.lower()
            mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "application/octet-stream"
            att_list.append({
                "filename": fn,
                "type": mime,
                "extracted": bool(content.strip())
            })
            
        full_json_payload = {
            "intent": summary.get("intent", "request_for_quotation"),
            "document_type": summary.get("document_type", ["RFQ"]),
            "buyer": summary.get("buyer", {
                "company_name": summary.get("sender", "N/A"),
                "address": "N/A",
                "gstin": "N/A",
                "contact_name": summary.get("sender", "N/A"),
                "contact_title": "N/A",
                "email": summary.get("sender", "N/A"),
                "phone": "N/A"
            }),
            "supplier": summary.get("supplier", {
                "company_name": "N/A",
                "address": "N/A",
                "contact_name": "N/A",
                "contact_title": "N/A",
                "email": "N/A"
            }),
            "rfq_number": summary.get("rfq_number", "N/A"),
            "rfq_issue_date": email_data.get("date", "N/A"),
            "quotation_due_date": summary.get("due_date", "N/A"),
            "items": summary.get("items", []),
            "commercial_terms": summary.get("commercial_terms", {}),
            "delivery_requirements": summary.get("delivery_requirements", {}),
            "shipping_details": summary.get("shipping_details", {}),
            "attachments": att_list,
            "missing_fields": summary.get("missing_fields", []),
            "conflicts": summary.get("conflicts", []),
            "confidence_score": summary.get("confidence_score", 0.95)
        }

    json_path = output_dir / f"{prefix}_extracted_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_json_payload, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved extraction outputs to: {output_dir}")
    return txt_path, json_path
