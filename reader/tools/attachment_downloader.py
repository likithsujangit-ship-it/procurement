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
    target_dir: Path,
    sender_email: str
) -> Path:
    """
    Downloads an individual attachment from a Gmail message and saves it to content-addressed storage.
    
    Args:
        service: Google API discovery resource.
        message_id: Gmail message ID.
        attachment_id: Gmail attachment ID.
        filename: Original name of the attachment file.
        target_dir: Directory where the file should be saved (fallback/logging context).
        sender_email: Sender email address to record in database.
        
    Returns:
        The Path to the saved file.
    """
    logger.info(f"Downloading attachment '{filename}' (ID: {attachment_id}) from message {message_id}...")
    
    try:
        # Fetch the attachment bytes from Gmail API
        attachment = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        
        file_data = base64.urlsafe_b64decode(attachment["data"].encode("utf-8"))
        
        # Sanitize filename to prevent path traversal, null bytes, or dangerous Windows reserved names
        import re
        safe_filename = Path(filename).name
        safe_filename = safe_filename.replace("\x00", "")
        safe_filename = re.sub(r'\.+[/\\]', '', safe_filename)
        
        stem = Path(safe_filename).stem
        suffix = Path(safe_filename).suffix.lower()
        clean_stem = "".join(c for c in stem if c.isalnum() or c in ("-", "_", "."))
        if not clean_stem:
            clean_stem = "unnamed_attachment"
            
        reserved_names = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
        if clean_stem.upper() in reserved_names:
            clean_stem = f"safe_{clean_stem}"
            
        safe_filename = f"{clean_stem}{suffix}"
        
        # Save using content-addressed storage
        from db.storage import save_attachment
        res = save_attachment(
            raw_bytes=file_data,
            original_filename=safe_filename,
            sender_email=sender_email
        )
        
        save_path = Path(res["path"])
        logger.info(f"Saved attachment to content-hash store: {save_path.resolve()} (Duplicate: {res['is_duplicate']})")
        return save_path

    except Exception as e:
        logger.error(f"Failed to download attachment '{filename}': {e}")
        raise e


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
        email = email_match.group(0).lower().strip()
        prefix = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in email).replace("@", "_")
        prefix = prefix or "unknown"
    else:
        prefix = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in sender_raw).replace("@", "_")
        prefix = prefix.strip().lower() or "unknown"

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

    # Format: DD-MM-YYYY-(HH_MM_SS_fff)
    time_folder_name = dt.strftime("%d-%m-%Y-(%H_%M_%S_%f)")[:-3]
    
    target_dir = Config.DOWNLOAD_DIR / prefix / time_folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Organizing files into subfolder: {target_dir.resolve()}")

    # 3. Download files into the content-addressed store
    for att in attachments:
        try:
            path = download_attachment(
                service=service,
                message_id=att["messageId"],
                attachment_id=att["attachmentId"],
                filename=att["filename"],
                target_dir=target_dir,
                sender_email=email
            )
            downloaded_paths.append(path)
        except Exception as e:
            logger.error(f"Skipping attachment download due to error: {e}")
            
    return downloaded_paths
