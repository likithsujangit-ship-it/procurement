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
DEFAULT_LIMIT = 100000  # Default Groq TPD limit on free tier


def _get_today_str() -> str:
    return date.today().isoformat()


def load_token_usage() -> dict:
    """Loads token usage data from reader/token_usage.json, resetting counter if new day or new API key."""
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
    Returns: (used_tokens, limit_tokens)
    """
    data = load_token_usage()
    
    used_match = re.search(r'\bUsed\s+(\d+)\b', error_message, re.I)
    limit_match = re.search(r'\bLimit\s+(\d+)\b', error_message, re.I)

    if used_match:
        data["used_tokens"] = int(used_match.group(1))
    if limit_match:
        data["limit_tokens"] = int(limit_match.group(1))

    save_token_usage(data)
    logger.info(f"[token_tracker] Updated token quota from 429 response: Used {data['used_tokens']} / Limit {data['limit_tokens']}")
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


