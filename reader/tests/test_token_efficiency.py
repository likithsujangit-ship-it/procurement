"""
Unit Tests for Token Efficiency Infrastructure (Disabled version).
"""

import pytest
from tools.token_tracker import (
    load_token_usage, save_token_usage, update_usage_from_429_error,
    check_preflight_quota, record_successful_usage
)

def test_token_tracker_is_disabled():
    """Verify that token tracker functions behave as disabled no-ops."""
    assert check_preflight_quota(9999999) is True
    assert load_token_usage()["used_tokens"] == 0
    assert update_usage_from_429_error("Error 429") == (0, 100000000)
