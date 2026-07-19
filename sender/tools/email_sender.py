"""
SMTP Sender Module for EMAIL SENDER.
Handles construction and transmission of multipart MIME emails with attachments, CC, and BCC.
Provides robust troubleshooting tips on failure.
"""

import smtplib
import socket
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional
from config import Config
from tools.utils import setup_logger

logger = setup_logger("email_sender")


class EmailAISendError(Exception):
    """Exception raised when email transmission fails."""
    pass


def send_email(
    recipients: List[str],
    subject: str,
    text_body: str,
    html_body: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    attachments: Optional[List[Path]] = None
) -> None:
    """
    Sends an email using the SMTP settings configured in Config.
    Supports CC, BCC, HTML, and multiple file attachments.
    
    Args:
        recipients: Main recipient email addresses.
        subject: Subject line.
        text_body: Plain text body.
        html_body: Rich HTML body.
        cc: Optional CC email addresses.
        bcc: Optional BCC email addresses.
        attachments: Optional list of validated Path objects to attach.
        
    Raises:
        EmailAISendError: If sending fails, containing specific troubleshooting info.
    """
    cc_list = cc or []
    bcc_list = bcc or []
    attach_list = attachments or []
    
    # 1. Check Dry Run
    if Config.DRY_RUN:
        logger.info("========== DRY RUN MODE ACTIVE ==========")
        logger.info(f"To: {recipients}")
        logger.info(f"CC: {cc_list}")
        logger.info(f"BCC: {bcc_list}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Attachments: {[p.name for p in attach_list]}")
        logger.info(f"Plain Text Preview:\n{text_body[:200]}...")
        logger.info("=========================================")
        logger.info("Dry run simulation successful. Email not sent.")
        return

    # 2. Construct Message
    msg = MIMEMultipart("mixed")
    msg["From"] = Config.SMTP_EMAIL
    msg["To"] = ", ".join(recipients)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject

    # Create the alternative part for text vs html content
    msg_alternative = MIMEMultipart("alternative")
    msg_alternative.attach(MIMEText(text_body, "plain", "utf-8"))
    msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(msg_alternative)

    # Attach files
    for filepath in attach_list:
        try:
            with open(filepath, "rb") as f:
                part = MIMEApplication(f.read(), Name=filepath.name)
            part["Content-Disposition"] = f'attachment; filename="{filepath.name}"'
            msg.attach(part)
            logger.debug(f"Attached file: {filepath.name}")
        except Exception as e:
            raise EmailAISendError(
                f"Failed to read/attach file '{filepath.name}': {e}\n"
                "Troubleshooting: Verify that the file is not locked by another application and has read permissions."
            )

    # 3. SMTP Send logic
    # Compile a list of all raw recipients (To, CC, BCC) for SMTP delivery envelope
    all_recipients = recipients + cc_list + bcc_list
    
    logger.info(f"Connecting to SMTP server {Config.SMTP_SERVER}:{Config.SMTP_PORT}...")
    try:
        # Start connection
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()  # Upgrade to TLS
        server.ehlo()
        
        logger.info(f"Authenticating as {Config.SMTP_EMAIL}...")
        server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
        
        logger.info(f"Sending MIME message to {len(all_recipients)} envelope recipients...")
        server.sendmail(Config.SMTP_EMAIL, all_recipients, msg.as_string())
        server.quit()
        
        logger.info("Email sent successfully!")
        
    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(f"Authentication failed: {auth_err}")
        raise EmailAISendError(
            "SMTP Authentication Failed.\n"
            f"Error details: {auth_err}\n"
            "Troubleshooting: Please double-check your credentials in sender/.env.\n"
            "If using Gmail, ensure 2-Factor Authentication is enabled and you generated a valid 'App Password'. "
            "Do NOT use your regular Gmail account login password."
        ) from auth_err
        
    except (socket.timeout, socket.error) as net_err:
        logger.error(f"Network error during SMTP operation: {net_err}")
        raise EmailAISendError(
            "Network Connection Timeout / Failure during email transmission.\n"
            f"Error details: {net_err}\n"
            "Troubleshooting: Check your internet connection and verify that your network/firewall "
            f"permits outbound TCP traffic on port {Config.SMTP_PORT} to {Config.SMTP_SERVER}."
        ) from net_err
        
    except smtplib.SMTPRecipientsRefused as ref_err:
        logger.error(f"Recipients refused: {ref_err}")
        raise EmailAISendError(
            "All recipients were refused by the SMTP mail server.\n"
            f"Error details: {ref_err}\n"
            "Troubleshooting: Verify that the email addresses in the recipient list are active and correctly typed."
        ) from ref_err
        
    except Exception as e:
        logger.error(f"Unhandled SMTP error: {e}")
        raise EmailAISendError(
            f"An unexpected SMTP/MIME error occurred: {e}\n"
            "Troubleshooting: Confirm your SMTP setup details in sender/.env and check mail server logs."
        ) from e
