"""
Validation Module for EMAIL SENDER.
Validates email formats and attachment existence with robust troubleshooting messages.
"""

import re
from pathlib import Path
from typing import List
from config import Config
from tools.utils import setup_logger

logger = setup_logger("validator")


class EmailAIValidationError(Exception):
    """Base Exception for validation issues in Email AI."""
    pass


class InvalidEmailError(EmailAIValidationError):
    """Exception raised when an email address is syntactically invalid."""
    def __init__(self, email: str, context: str = "recipient"):
        super().__init__(
            f"Invalid email address found in {context}: '{email}'\n"
            "Troubleshooting: Please check the spelling, format, and ensure it contains an '@' symbol and a valid domain (e.g. user@example.com)."
        )


class MissingAttachmentError(EmailAIValidationError):
    """Exception raised when a requested attachment does not exist on disk."""
    def __init__(self, filename: str):
        expected_path = Config.FILES_DIR / filename
        super().__init__(
            f"Requested attachment file '{filename}' was not found.\n"
            f"Expected file location: {expected_path.resolve()}\n"
            "Troubleshooting: Please copy the file to the 'sender/files/' folder and verify the filename spelling (case-sensitive)."
        )


def validate_email(email: str, context: str = "recipient") -> None:
    """
    Validates a single email address using standard RFC 5322 regex.
    Raises InvalidEmailError if invalid.
    """
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9-]{2,}$'
    if not re.match(email_regex, email.strip()):
        logger.error(f"Validation failed for email: {email}")
        raise InvalidEmailError(email, context)


def validate_attachments(filenames: List[str]) -> List[Path]:
    """
    Validates that all specified attachment files exist in the sender/files directory.
    Raises MissingAttachmentError if any file is missing.
    
    Returns:
        List of Path objects for the valid attachments.
    """
    valid_paths: List[Path] = []
    for filename in filenames:
        file_path = Config.FILES_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            logger.error(f"Validation failed: attachment '{filename}' does not exist.")
            raise MissingAttachmentError(filename)
        valid_paths.append(file_path)
        logger.debug(f"Attachment verified: {file_path}")
    return valid_paths
