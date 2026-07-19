"""
Link and Pattern Extraction Module.
Uses regex to extract links (Google Drive, OneDrive, GitHub, general URLs),
email addresses, phone numbers, OTPs, tracking numbers, and reference numbers.
"""

import re
from typing import Dict, List, Any
from tools.utils import setup_logger

logger = setup_logger("link_extractor")


def extract_resources(text: str) -> Dict[str, List[str]]:
    """
    Parses body text using regular expressions to extract key resources and identifiers.
    
    Args:
        text: Raw email body text.
        
    Returns:
        A dictionary containing categorized lists of extracted items.
    """
    logger.debug("Extracting links and pattern resources from text.")
    
    # 1. URL extraction patterns
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    urls = re.findall(url_pattern, text)
    
    google_drive_links = []
    onedrive_links = []
    github_links = []
    general_urls = []
    
    for url in urls:
        # Clean trailing punctuation
        cleaned_url = url.rstrip('.,;()[]{}')
        
        if "drive.google.com" in cleaned_url or "docs.google.com" in cleaned_url:
            google_drive_links.append(cleaned_url)
        elif "onedrive.live.com" in cleaned_url or "sharepoint.com" in cleaned_url:
            onedrive_links.append(cleaned_url)
        elif "github.com" in cleaned_url:
            github_links.append(cleaned_url)
        else:
            general_urls.append(cleaned_url)

    # De-duplicate lists
    google_drive_links = list(dict.fromkeys(google_drive_links))
    onedrive_links = list(dict.fromkeys(onedrive_links))
    github_links = list(dict.fromkeys(github_links))
    general_urls = list(dict.fromkeys(general_urls))

    # 2. Email Address pattern
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    emails = list(dict.fromkeys(re.findall(email_pattern, text)))

    # 3. Phone Number patterns (supports formats: +1-123-456-7890, 1234567890, (123) 456-7890)
    phone_pattern = r'\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    raw_phones = re.findall(phone_pattern, text)
    phones = []
    for phone in raw_phones:
        cleaned = phone.strip()
        # Ensure it has at least 7 digits to prevent matching small random numbers
        if sum(c.isdigit() for c in cleaned) >= 7:
            phones.append(cleaned)
    phones = list(dict.fromkeys(phones))

    # 4. OTP Patterns (e.g. "OTP: 123456", "verification code 123456", "OTP is 1234")
    otp_matches = re.findall(
        r'\b(?:otp|one[- ]time[- ]password|verification[- ]code|code|pin)\b[:\s-]*(?:is[:\s-]*)?(\d{4,8})\b',
        text,
        re.IGNORECASE
    )
    otps = list(dict.fromkeys(otp_matches))

    # 5. Tracking / Reference / Invoice Number patterns
    # e.g., tracking ID: 1Z999AA10123456784, Invoice #1024, Ref No: 9876543
    tracking_pattern = r'\b(?:tracking|track|package|shipment)\b[:\s#\-]*(1Z[0-9A-Z]{16}|[0-9]{10,22})\b'
    tracking_numbers = list(dict.fromkeys(re.findall(tracking_pattern, text, re.IGNORECASE)))

    invoice_pattern = r'\b(?:invoice|bill|receipt)\b[:\s#\-]*([a-zA-Z0-9\-]{4,15})\b'
    invoices = list(dict.fromkeys(re.findall(invoice_pattern, text, re.IGNORECASE)))

    ref_pattern = r'\b(?:ref|reference|ticket|order|booking)\b[:\s#\-]*([a-zA-Z0-9\-]{5,20})\b'
    reference_numbers = list(dict.fromkeys(re.findall(ref_pattern, text, re.IGNORECASE)))

    return {
        "google_drive_links": google_drive_links,
        "onedrive_links": onedrive_links,
        "github_links": github_links,
        "general_urls": general_urls,
        "emails": emails,
        "phones": phones,
        "otps": otps,
        "tracking_numbers": tracking_numbers,
        "invoices": invoices,
        "reference_numbers": reference_numbers
    }
