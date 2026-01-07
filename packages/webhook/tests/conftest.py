"""Test configuration and fixtures for webhook package tests."""

import os
import pytest

# Set test environment variables before any app imports
# These must be set at module level to ensure they're available
# when test_authentication.py imports devs_webhook.app
os.environ.setdefault('GITHUB_WEBHOOK_SECRET', 'test_secret_for_ci')
os.environ.setdefault('GITHUB_TOKEN', 'test_token_for_ci')
os.environ.setdefault('GITHUB_MENTIONED_USER', 'testuser')
os.environ.setdefault('ADMIN_PASSWORD', 'test_admin_password')
os.environ.setdefault('DEV_MODE', 'true')


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset the config cache and deduplication cache before each test to ensure clean state."""
    from devs_webhook.config import get_config
    from devs_webhook.core.deduplication import clear_cache
    get_config.cache_clear()
    clear_cache()
    yield
    get_config.cache_clear()
    clear_cache()
