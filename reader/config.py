"""
Configuration Module for EMAIL READER.
Loads environment variables, initializes directories, and validates setup.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory of the reader project
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
    CREDENTIALS_PATH: Path = BASE_DIR / os.getenv("CREDENTIALS_PATH", "credentials.json")
    TOKEN_PATH: Path = BASE_DIR / os.getenv("TOKEN_PATH", "token.json")
    DOWNLOAD_DIR: Path = BASE_DIR / os.getenv("DOWNLOAD_DIR", "files")
    OUTPUTS_DIR: Path = BASE_DIR / os.getenv("OUTPUTS_DIR", "outputs")
    LOGS_DIR: Path = BASE_DIR / "logs"

    # API Keys
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # Reader Settings
    DEFAULT_MAX_RESULTS: int = int(os.getenv("DEFAULT_MAX_RESULTS", "5"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls) -> None:
        """
        Validates the configuration.
        Raises ValueError if critical variables are missing.
        """
        errors = []

        has_groq = cls.GROQ_API_KEY and cls.GROQ_API_KEY != "gsk_your_groq_api_key_here"
        has_openrouter = bool(cls.OPENROUTER_API_KEY)
        if not has_groq and not has_openrouter:
            errors.append("Neither GROQ_API_KEY nor OPENROUTER_API_KEY is configured.")

        if not cls.CREDENTIALS_PATH.exists():
            errors.append(
                f"credentials.json not found at {cls.CREDENTIALS_PATH}. "
                "Please perform the Google Cloud OAuth setup and download your credentials.json file."
            )

        if errors:
            raise ValueError(
                "Configuration Validation Failed:\n" + 
                "\n".join(f"- {err}" for err in errors) + 
                "\n\nPlease update your reader/.env file and ensure credentials.json is present."
            )


# Initialize directories
Config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
Config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
