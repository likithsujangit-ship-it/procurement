"""
Token Usage & Quota Tracker Module (Disabled/No-op Version).
All checks and tracking are disabled, allowing direct execution of API requests without filesystem state.
"""

from typing import Tuple

def load_token_usage() -> dict:
    return {
        "date": "2026-07-23",
        "api_key_prefix": "gsk_",
        "used_tokens": 0,
        "limit_tokens": 100000000,
        "last_updated": ""
    }

def save_token_usage(data: dict) -> None:
    pass

def update_usage_from_429_error(error_message: str) -> Tuple[int, int]:
    return 0, 100000000

def record_successful_usage(tokens_used: int) -> None:
    pass

def check_preflight_quota(estimated_tokens: int) -> bool:
    return True
