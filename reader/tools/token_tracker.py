"""
Token Usage & Quota Tracker Module.
Maintains reader/token_usage.json tracking daily cumulative token usage, parses 429 rate limit errors
to synchronize usage metrics, and performs preflight quota checks before API requests.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Tuple, Optional
from tools.utils import setup_logger
from config import Config

logger = setup_logger("token_tracker")

READER_DIR = Path(__file__).resolve().parent.parent
USAGE_FILE = READER_DIR / "token_usage.json"
DEFAULT_LIMIT = 1000000  # Default limit set higher to accommodate higher tier keys before hitting actual 429s


def _get_today_str() -> str:
    return date.today().isoformat()


def load_token_usage() -> dict:
    """Loads token usage data from reader/token_usage.json, resetting counter if new day or new API key."""
    # Dynamically reload dotenv to catch any manual changes to .env on the fly
    from dotenv import load_dotenv
    import os
    env_path = READER_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        new_key = os.getenv("GROQ_API_KEY", "")
        if new_key:
            Config.GROQ_API_KEY = new_key
            
    today = _get_today_str()
    current_key_prefix = Config.GROQ_API_KEY[:15] if Config.GROQ_API_KEY else "none"

    if USAGE_FILE.exists():
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            saved_date = data.get("date")
            saved_key_prefix = data.get("api_key_prefix", "")
            
            if saved_date == today and saved_key_prefix == current_key_prefix:
                return data
        except Exception as e:
            logger.warning(f"Failed to load token usage file: {e}")

    data = {
        "date": today,
        "api_key_prefix": current_key_prefix,
        "used_tokens": 0,
        "limit_tokens": DEFAULT_LIMIT,
        "last_updated": datetime.now().isoformat()
    }
    save_token_usage(data)
    return data


def save_token_usage(data: dict) -> None:
    """Saves token usage data to reader/token_usage.json."""
    try:
        data["last_updated"] = datetime.now().isoformat()
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save token usage: {e}")


def update_usage_from_429_error(error_message: str) -> Tuple[int, int]:
    """
    Parses 'Used X' and 'Limit Y' from a 429 error message string to update daily token usage.
    Only updates if it is a daily limit (TPD) error to avoid corrupting limits with per-minute limits (TPM).
    Returns: (used_tokens, limit_tokens)
    """
    data = load_token_usage()
    
    # Check if the error is actually a daily limit error
    if "tpd" in error_message.lower() or "tokens per day" in error_message.lower() or re.search(r'\bday\b', error_message, re.I):
        used_match = re.search(r'\bUsed\s+(\d+)\b', error_message, re.I)
        limit_match = re.search(r'\bLimit\s+(\d+)\b', error_message, re.I)

        if used_match:
            data["used_tokens"] = int(used_match.group(1))
        if limit_match:
            data["limit_tokens"] = int(limit_match.group(1))

        save_token_usage(data)
        logger.info(f"[token_tracker] Updated token quota from daily 429 response: Used {data['used_tokens']} / Limit {data['limit_tokens']}")
    else:
        logger.info(f"[token_tracker] Ignored per-minute/request 429 response limit: {error_message}")
        
    return data["used_tokens"], data["limit_tokens"]


def record_successful_usage(tokens_used: int) -> None:
    """Increments cumulative token count by tokens_used."""
    data = load_token_usage()
    data["used_tokens"] += tokens_used
    save_token_usage(data)


def check_preflight_quota(estimated_tokens: int) -> bool:
    """
    Estimates token cost and checks against remaining daily quota.
    Returns True if within budget, False if request would exceed limit.
    """
    data = load_token_usage()
    used = data.get("used_tokens", 0)
    limit = data.get("limit_tokens", DEFAULT_LIMIT)

    if used + estimated_tokens >= limit:
        logger.warning(
            f"[token_tracker] Preflight check failed: Estimated cost {estimated_tokens} + used {used} "
            f"exceeds daily limit {limit}. Failing fast before hitting 429."
        )
        return False
    return True


