"""Tests for separate container pool functionality."""

import pytest
from unittest.mock import patch
from devs_webhook.config import WebhookConfig


class TestContainerPoolConfig:
    """Test container pool configuration."""

    def test_default_container_pool(self):
        """Test default container pool configuration."""
        config = WebhookConfig()
        assert config.get_container_pool_list() == ["eamonn", "harry", "darren"]

    def test_custom_container_pool(self):
        """Test custom container pool configuration."""
        with patch.dict('os.environ', {'CONTAINER_POOL': 'alice,bob,charlie'}):
            config = WebhookConfig()
            assert config.get_container_pool_list() == ['alice', 'bob', 'charlie']

    def test_test_container_pool_empty_defaults_to_main(self):
        """Test that empty test_container_pool falls back to main pool."""
        with patch.dict('os.environ', {'CONTAINER_POOL': 'alice,bob'}):
            config = WebhookConfig()
            # test_container_pool is empty, should fall back to main pool
            assert config.get_test_container_pool_list() == ['alice', 'bob']

    def test_test_container_pool_configured(self):
        """Test that configured test_container_pool is used."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob',
            'TEST_CONTAINER_POOL': 'charlie,dave'
        }):
            config = WebhookConfig()
            assert config.get_test_container_pool_list() == ['charlie', 'dave']
            # Main pool unchanged
            assert config.get_container_pool_list() == ['alice', 'bob']

    def test_claude_container_pool_empty_defaults_to_main(self):
        """Test that empty claude_container_pool falls back to main pool."""
        with patch.dict('os.environ', {'CONTAINER_POOL': 'alice,bob'}):
            config = WebhookConfig()
            # claude_container_pool is empty, should fall back to main pool
            assert config.get_claude_container_pool_list() == ['alice', 'bob']

    def test_claude_container_pool_configured(self):
        """Test that configured claude_container_pool is used."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob',
            'CLAUDE_CONTAINER_POOL': 'eve,frank'
        }):
            config = WebhookConfig()
            assert config.get_claude_container_pool_list() == ['eve', 'frank']
            # Main pool unchanged
            assert config.get_container_pool_list() == ['alice', 'bob']

    def test_both_separate_pools_configured(self):
        """Test both test and claude pools configured separately."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob',
            'TEST_CONTAINER_POOL': 'charlie,dave',
            'CLAUDE_CONTAINER_POOL': 'eve,frank'
        }):
            config = WebhookConfig()
            assert config.get_container_pool_list() == ['alice', 'bob']
            assert config.get_test_container_pool_list() == ['charlie', 'dave']
            assert config.get_claude_container_pool_list() == ['eve', 'frank']

    def test_overlapping_pools(self):
        """Test pools with overlapping container names."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob,charlie',
            'TEST_CONTAINER_POOL': 'bob,charlie,dave',
            'CLAUDE_CONTAINER_POOL': 'charlie,eve'
        }):
            config = WebhookConfig()
            assert config.get_container_pool_list() == ['alice', 'bob', 'charlie']
            assert config.get_test_container_pool_list() == ['bob', 'charlie', 'dave']
            assert config.get_claude_container_pool_list() == ['charlie', 'eve']

    def test_get_pool_for_task_type_tests(self):
        """Test get_pool_for_task_type returns test pool for 'tests' task type."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob',
            'TEST_CONTAINER_POOL': 'charlie,dave'
        }):
            config = WebhookConfig()
            assert config.get_pool_for_task_type('tests') == ['charlie', 'dave']

    def test_get_pool_for_task_type_claude(self):
        """Test get_pool_for_task_type returns claude pool for 'claude' task type."""
        with patch.dict('os.environ', {
            'CONTAINER_POOL': 'alice,bob',
            'CLAUDE_CONTAINER_POOL': 'eve,frank'
        }):
            config = WebhookConfig()
            assert config.get_pool_for_task_type('claude') == ['eve', 'frank']

    def test_get_pool_for_task_type_unknown(self):
        """Test get_pool_for_task_type returns main pool for unknown task type."""
        with patch.dict('os.environ', {'CONTAINER_POOL': 'alice,bob'}):
            config = WebhookConfig()
            assert config.get_pool_for_task_type('unknown') == ['alice', 'bob']

    def test_get_pool_for_task_type_fallback(self):
        """Test get_pool_for_task_type falls back to main pool when specific pool not configured."""
        with patch.dict('os.environ', {'CONTAINER_POOL': 'alice,bob'}):
            config = WebhookConfig()
            # No test or claude pool configured, should fall back to main
            assert config.get_pool_for_task_type('tests') == ['alice', 'bob']
            assert config.get_pool_for_task_type('claude') == ['alice', 'bob']

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly in pool names."""
        with patch.dict('os.environ', {
            'TEST_CONTAINER_POOL': ' charlie , dave , eve '
        }):
            config = WebhookConfig()
            assert config.get_test_container_pool_list() == ['charlie', 'dave', 'eve']

    def test_empty_entries_ignored(self):
        """Test that empty entries in comma-separated list are ignored."""
        with patch.dict('os.environ', {
            'TEST_CONTAINER_POOL': 'charlie,,dave,,,eve'
        }):
            config = WebhookConfig()
            assert config.get_test_container_pool_list() == ['charlie', 'dave', 'eve']
