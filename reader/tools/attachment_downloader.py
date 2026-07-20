"""
Attachment Downloader Module.
Interacts with the Gmail API to download and save binary files to user-specific subfolders.
"""

import base64
import re
from pathlib import Path
from typing import List, Dict, Any
from googleapiclient.discovery import Resource
from config import Config
from tools.utils import setup_logger

logger = setup_logger("attachment_downloader")


def download_attachment(
    service: Resource,
    message_id: str,
    attachment_id: str,
    filename: str,
    target_dir: Path
) -> Path:
    """
    Downloads an individual attachment from a Gmail message and saves it to target_dir.
    
    Args:
        service: Google API discovery resource.
        message_id: Gmail message ID.
        attachment_id: Gmail attachment ID.
        filename: Original name of the attachment file.
        target_dir: Directory where the file should be saved.
        
    Returns:
        The Path to the saved file.
    """
    # Check if file already exists in target_dir or sender's subfolders
    save_path = target_dir / filename
    sender_dir = target_dir.parent
    existing_matches = [p for p in sender_dir.glob(f"**/{filename}") if p.is_file()] if sender_dir.exists() else []

    if save_path.exists():
        print(f"Attachment '{filename}' already exists.")
        logger.info(f"Attachment '{filename}' already exists at {save_path.resolve()}. Skipping redownload.")
        return save_path
    elif existing_matches:
        existing_path = existing_matches[0]
        print(f"Attachment '{filename}' already exists.")
        logger.info(f"Attachment '{filename}' already exists at {existing_path.resolve()}. Skipping redownload.")
        return existing_path

    logger.info(f"Downloading attachment '{filename}' (ID: {attachment_id}) from message {message_id}...")
    
    try:
        # Fetch the attachment bytes from Gmail API
        attachment = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        
        file_data = base64.urlsafe_b64decode(attachment["data"].encode("utf-8"))
        
        # Write to disk
        with open(save_path, "wb") as f:
            f.write(file_data)
            
        logger.info(f"Saved attachment to: {save_path.resolve()}")
        return save_path

    except Exception as e:
        logger.error(f"Failed to download attachment '{filename}': {e}")
        raise


def download_all_attachments(
    service: Resource,
    email_data: Dict[str, Any]
) -> List[Path]:
    """
    Downloads all attachments found in the email metadata.
    Saves them in reader/files/<sender_prefix>/.
    
    Args:
        service: Google API discovery resource.
        email_data: Parsed email detail dictionary.
        
    Returns:
        List of Path objects for all downloaded files.
    """
    downloaded_paths = []
    attachments = email_data.get("attachments", [])
    
    if not attachments:
        logger.debug(f"No attachments to download for email ID {email_data['id']}.")
        return []

    # 1. Parse sender email prefix
    sender_raw = email_data.get("sender", "")
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', sender_raw)
    if email_match:
        email = email_match.group(0)
    else:
        email = sender_raw.strip().lower()
        
    prefix = email.split("@")[0].strip() if "@" in email else email
    # Clean the prefix to make it a valid folder name
    prefix = "".join(c for c in prefix if c.isalnum() or c in ("-", "_", "."))
    if not prefix:
        prefix = "unknown"

    # 2. Create the organizer subfolder with date/month/year-(time) with milliseconds
    from datetime import datetime
    internal_date_ms = email_data.get("internalDate")
    if internal_date_ms:
        try:
            dt = datetime.fromtimestamp(int(internal_date_ms) / 1000.0)
        except Exception:
            dt = datetime.now()
    else:
        dt = datetime.now()

    # Format: dd / mm / yyyy - (xxH : yyM : zzS) as a single flat folder name
    time_folder_name = f"{dt.day:02d} ∕ {dt.month:02d} ∕ {dt.year} - ({dt.hour:02d}H : {dt.minute:02d}M : {dt.second:02d}S)"
    
    target_dir = Config.DOWNLOAD_DIR / prefix / time_folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Organizing files into subfolder: {target_dir.resolve()}")

    # 3. Download files into the subfolder
    for att in attachments:
        try:
            path = download_attachment(
                service=service,
                message_id=att["messageId"],
                attachment_id=att["attachmentId"],
                filename=att["filename"],
                target_dir=target_dir
            )
            downloaded_paths.append(path)
        except Exception as e:
            logger.error(f"Skipping attachment download due to error: {e}")
            
    return downloaded_paths
