"""
Gmail Reader Module.
Fetches list of emails and individual email details based on various search filters.
"""

import base64
from datetime import datetime
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import Resource
from tools.utils import setup_logger

logger = setup_logger("gmail_reader")


def build_search_query(
    senders: Optional[List[str]] = None,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    has_attachments: bool = False,
    is_unread: bool = False,
    is_starred: bool = False,
    is_important: bool = False,
    custom_query: Optional[str] = None
) -> str:
    """
    Builds a Gmail search query string from various parameter filters.
    
    Args:
        senders: List of sender email addresses/names.
        after_date: Date string (YYYY/MM/DD).
        before_date: Date string (YYYY/MM/DD).
        has_attachments: Filter for emails with attachments.
        is_unread: Filter for unread emails.
        is_starred: Filter for starred emails.
        is_important: Filter for important emails.
        custom_query: Any arbitrary custom query to append.
        
    Returns:
        Gmail search query string.
    """
    parts = []

    if senders:
        sender_query = " OR ".join(f"from:{s.strip()}" for s in senders)
        if len(senders) > 1:
            parts.append(f"({sender_query})")
        else:
            parts.append(sender_query)

    if after_date:
        parts.append(f"after:{after_date}")
    
    if before_date:
        parts.append(f"before:{before_date}")

    if has_attachments:
        parts.append("has:attachment")

    if is_unread:
        parts.append("is:unread")

    if is_starred:
        parts.append("is:starred")

    if is_important:
        parts.append("is:important")

    if custom_query:
        parts.append(custom_query)

    query = " ".join(parts)
    logger.debug(f"Constructed Gmail query: '{query}'")
    return query


def fetch_emails(
    service: Resource,
    query: str = "",
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Fetches message metadata from Gmail API matching the search query.
    
    Args:
        service: Google API discovery resource.
        query: Gmail search query string.
        max_results: Max number of messages to fetch.
        
    Returns:
        List of dicts representing detailed emails.
    """
    logger.info(f"Fetching up to {max_results} emails matching query: '{query}'")
    
    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        
        messages = results.get("messages", [])
        if not messages:
            logger.info("No messages found matching search query.")
            return []

        detailed_emails = []
        for msg in messages:
            try:
                email_detail = fetch_email_details(service, msg["id"])
                detailed_emails.append(email_detail)
            except Exception as e:
                logger.error(f"Failed to fetch details for message ID {msg['id']}: {e}")
                
        return detailed_emails

    except Exception as e:
        logger.error(f"Failed to query messages list from Gmail: {e}")
        raise


def fetch_email_details(service: Resource, msg_id: str) -> Dict[str, Any]:
    """
    Retrieves detailed headers, body content, and attachment metadata for a message.
    
    Args:
        service: Google API discovery resource.
        msg_id: Gmail message ID.
        
    Returns:
        A dictionary containing parsed email details.
    """
    logger.debug(f"Fetching details for message ID: {msg_id}")
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    
    email_data = {
        "id": msg_id,
        "threadId": msg.get("threadId"),
        "internalDate": msg.get("internalDate"),
        "subject": "No Subject",
        "sender": "Unknown",
        "date": "",
        "body": "",
        "html_body": "",
        "attachments": []
    }

    # Extract standard headers
    for header in headers:
        name = header["name"].lower()
        if name == "subject":
            email_data["subject"] = header["value"]
        elif name == "from":
            email_data["sender"] = header["value"]
        elif name == "date":
            email_data["date"] = header["value"]

    # Parse body and attachments from payload parts
    _parse_parts(service, msg_id, payload, email_data)
    
    return email_data


def _parse_parts(service: Resource, msg_id: str, part: Dict[str, Any], email_data: Dict[str, Any]) -> None:
    """Recursively parses email MIME parts to extract body text and attachments."""
    mime_type = part.get("mimeType", "")
    filename = part.get("filename", "")
    body = part.get("body", {})
    data = body.get("data", "")
    
    # 1. Capture text bodies
    if mime_type == "text/plain" and data and not filename:
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        email_data["body"] += decoded
    elif mime_type == "text/html" and data and not filename:
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        email_data["html_body"] += decoded
        
    # 2. Capture attachments metadata
    elif filename:
        attachment_id = body.get("attachmentId", "")
        size = body.get("size", 0)
        email_data["attachments"].append({
            "filename": filename,
            "mimeType": mime_type,
            "attachmentId": attachment_id,
            "size": size,
            "messageId": msg_id
        })
        logger.debug(f"Found attachment metadata: '{filename}' (size: {size} bytes)")
        
    # Recurse if there are sub-parts
    parts = part.get("parts", [])
    for subpart in parts:
        _parse_parts(service, msg_id, subpart, email_data)
