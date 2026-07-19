"""
Contacts lookup module for EMAIL SENDER.
Resolves names (e.g., 'hr', 'manager') to email addresses.
"""

from typing import Dict, Optional
from tools.utils import setup_logger

logger = setup_logger("contacts")

# Default contact directory (can be extended to load from a JSON/CSV file)
CONTACTS_DATABASE: Dict[str, str] = {
    "hr": "hr@gmail.com",
    "manager": "manager@gmail.com",
    "admin": "admin@gmail.com",
    "support": "support@gmail.com",
    "billing": "billing@gmail.com"
}


def resolve_contact(name_or_email: str) -> str:
    """
    Resolves a name to an email address. If it's already an email, returns it.
    
    Args:
        name_or_email: A contact name (e.g. 'hr') or a raw email address.
        
    Returns:
        The resolved email address.
    """
    cleaned = name_or_email.strip().lower()
    
    # If it contains '@', assume it is already a raw email address
    if "@" in cleaned:
        return cleaned

    # Check database
    if cleaned in CONTACTS_DATABASE:
        resolved = CONTACTS_DATABASE[cleaned]
        logger.debug(f"Resolved contact '{name_or_email}' to '{resolved}'")
        return resolved

    # Fallback to appending a generic domain or returning as is (validator will catch it)
    logger.warning(f"Contact name '{name_or_email}' not found in database. Returning as is.")
    return name_or_email
