"""
Configuration Module for EMAIL SENDER.
Loads environment variables and sets up project paths.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Base Directory of the sender project
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fallback to general environment
    load_dotenv()


class Config:
    """Configuration class that loads and validates environment variables."""

    # Paths
    FILES_DIR: Path = BASE_DIR / "files"
    OUTPUTS_DIR: Path = BASE_DIR / "outputs"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # API Keys
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # SMTP Configuration
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL: str = os.getenv("SMTP_EMAIL", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

    # Application Settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    DRY_RUN: bool = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls) -> None:
        """
        Validates the configuration.
        Raises ValueError if critical variables are missing.
        """
        errors = []

        if not cls.GROQ_API_KEY or cls.GROQ_API_KEY == "gsk_your_groq_api_key_here":
            errors.append("GROQ_API_KEY is not configured.")

        if not cls.DRY_RUN:
            if not cls.SMTP_EMAIL or cls.SMTP_EMAIL == "your_email@gmail.com":
                errors.append("SMTP_EMAIL is not configured or contains placeholder.")
            if not cls.SMTP_PASSWORD or cls.SMTP_PASSWORD == "your_gmail_app_password_here":
                errors.append("SMTP_PASSWORD is not configured or contains placeholder.")

        if errors:
            raise ValueError(
                "Configuration Validation Failed:\n" + 
                "\n".join(f"- {err}" for err in errors) + 
                "\n\nPlease update your sender/.env file with correct credentials."
            )


# Initialize directories
Config.FILES_DIR.mkdir(parents=True, exist_ok=True)
Config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
