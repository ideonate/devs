"""Test authorized trigger users functionality."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from devs_webhook.config import WebhookConfig
from devs_webhook.core.webhook_handler import WebhookHandler
from devs_webhook.github.models import IssueEvent, GitHubRepository, GitHubUser, GitHubIssue
import json


class TestAuthorizedUsers:
    """Test cases for authorized trigger users feature (Claude dispatch)."""

    def test_config_parses_authorized_users(self):
        """Test that config correctly parses authorized trigger users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob,charlie'
        }):
            config = WebhookConfig()
            users = config.get_authorized_trigger_users_list()
            assert users == ['alice', 'bob', 'charlie']

    def test_config_handles_empty_authorized_users(self):
        """Test that empty authorized users list allows all."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': ''
        }):
            config = WebhookConfig()
            users = config.get_authorized_trigger_users_list()
            assert users == []
            # Should allow any user when list is empty
            assert config.is_user_authorized_to_trigger('anyone') == True

    def test_config_handles_whitespace_in_users(self):
        """Test that whitespace is properly handled in user list."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': ' alice , bob , charlie '
        }):
            config = WebhookConfig()
            users = config.get_authorized_trigger_users_list()
            assert users == ['alice', 'bob', 'charlie']

    def test_is_user_authorized_with_configured_users(self):
        """Test authorization check with configured users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob'
        }):
            config = WebhookConfig()

            # Authorized users
            assert config.is_user_authorized_to_trigger('alice') == True
            assert config.is_user_authorized_to_trigger('Bob') == True  # Case insensitive
            assert config.is_user_authorized_to_trigger('ALICE') == True

            # Unauthorized users
            assert config.is_user_authorized_to_trigger('charlie') == False
            assert config.is_user_authorized_to_trigger('unknown') == False

    def test_is_user_authorized_empty_allows_all(self):
        """Test that empty authorized list allows all users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': ''
        }):
            config = WebhookConfig()

            # All users should be allowed
            assert config.is_user_authorized_to_trigger('anyone') == True
            assert config.is_user_authorized_to_trigger('random') == True
            assert config.is_user_authorized_to_trigger('user123') == True


class TestAuthorizedCIUsers:
    """Test cases for authorized CI trigger users feature (test dispatch)."""

    def test_config_parses_authorized_ci_users(self):
        """Test that config correctly parses authorized CI trigger users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_CI_TRIGGER_USERS': 'alice,bob,botuser'
        }):
            config = WebhookConfig()
            users = config.get_authorized_ci_trigger_users_list()
            assert users == ['alice', 'bob', 'botuser']

    def test_config_handles_empty_authorized_ci_users(self):
        """Test that empty authorized CI users list allows all."""
        with patch.dict('os.environ', {
            'AUTHORIZED_CI_TRIGGER_USERS': ''
        }):
            config = WebhookConfig()
            users = config.get_authorized_ci_trigger_users_list()
            assert users == []
            # Should allow any user when list is empty
            assert config.is_user_authorized_for_ci('anyone') == True

    def test_config_handles_whitespace_in_ci_users(self):
        """Test that whitespace is properly handled in CI user list."""
        with patch.dict('os.environ', {
            'AUTHORIZED_CI_TRIGGER_USERS': ' alice , bob , botuser '
        }):
            config = WebhookConfig()
            users = config.get_authorized_ci_trigger_users_list()
            assert users == ['alice', 'bob', 'botuser']

    def test_is_user_authorized_for_ci_with_configured_users(self):
        """Test CI authorization check with configured users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_CI_TRIGGER_USERS': 'alice,bob,botuser'
        }):
            config = WebhookConfig()

            # Authorized users (including bot)
            assert config.is_user_authorized_for_ci('alice') == True
            assert config.is_user_authorized_for_ci('Bob') == True  # Case insensitive
            assert config.is_user_authorized_for_ci('botuser') == True  # Bot can trigger CI

            # Unauthorized users
            assert config.is_user_authorized_for_ci('charlie') == False
            assert config.is_user_authorized_for_ci('unknown') == False

    def test_is_user_authorized_for_ci_empty_allows_all(self):
        """Test that empty authorized CI list allows all users."""
        with patch.dict('os.environ', {
            'AUTHORIZED_CI_TRIGGER_USERS': ''
        }):
            config = WebhookConfig()

            # All users should be allowed
            assert config.is_user_authorized_for_ci('anyone') == True
            assert config.is_user_authorized_for_ci('botuser') == True

    def test_separate_lists_for_claude_and_ci(self):
        """Test that Claude and CI have separate authorization lists."""
        with patch.dict('os.environ', {
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob',  # Humans only
            'AUTHORIZED_CI_TRIGGER_USERS': 'alice,bob,botuser'  # Humans + bot
        }):
            config = WebhookConfig()

            # Bot is authorized for CI but not for Claude dispatch
            assert config.is_user_authorized_to_trigger('botuser') == False
            assert config.is_user_authorized_for_ci('botuser') == True

            # Humans are authorized for both
            assert config.is_user_authorized_to_trigger('alice') == True
            assert config.is_user_authorized_for_ci('alice') == True


class TestWebhookHandlerAuthorization:
    """Integration tests for webhook handler authorization."""

    @pytest.mark.asyncio
    async def test_webhook_handler_blocks_unauthorized_user(self):
        """Test that webhook handler blocks unauthorized users for Claude dispatch."""
        from devs_webhook.config import get_config

        with patch.dict('os.environ', {
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_MENTIONED_USER': 'botuser',
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob',
            'ALLOWED_ORGS': 'testorg',
            'DEV_MODE': 'true'
        }):
            # Clear the config cache inside patch context so new config gets patched env
            get_config.cache_clear()
            handler = WebhookHandler()
            try:
                # Mock ensure_repo_config to avoid actual repo cloning
                from devs_common.devs_config import DevsOptions
                handler.container_pool.ensure_repo_config = AsyncMock(return_value=DevsOptions())

                # Create a mock event from unauthorized user
                headers = {'x-github-event': 'issues'}
                payload = json.dumps({
                    'action': 'opened',
                    'repository': {
                        'id': 1,
                        'name': 'testrepo',
                        'full_name': 'testorg/testrepo',
                        'owner': {
                            'login': 'testorg',
                            'id': 1,
                            'avatar_url': 'http://example.com',
                            'html_url': 'http://example.com'
                        },
                        'html_url': 'http://example.com',
                        'clone_url': 'http://example.com',
                        'ssh_url': 'http://example.com',
                        'default_branch': 'main'
                    },
                    'sender': {
                        'login': 'unauthorized_user',  # Not in authorized list
                        'id': 999,
                        'avatar_url': 'http://example.com',
                        'html_url': 'http://example.com'
                    },
                    'issue': {
                        'id': 1,
                        'number': 1,
                        'title': 'Test issue',
                        'body': '@botuser please help',
                        'state': 'open',
                        'user': {
                            'login': 'unauthorized_user',
                            'id': 999,
                            'avatar_url': 'http://example.com',
                            'html_url': 'http://example.com'
                        },
                        'html_url': 'http://example.com',
                        'created_at': '2024-01-01T00:00:00Z',
                        'updated_at': '2024-01-01T00:00:00Z'
                    }
                }).encode()

                # Mock the container pool to track if task was queued
                handler.container_pool.queue_task = AsyncMock(return_value=True)

                # Process the webhook
                await handler.process_webhook(headers, payload, 'test-delivery-id')

                # Task should NOT have been queued due to unauthorized user
                handler.container_pool.queue_task.assert_not_called()
            finally:
                # Clean up async workers
                await handler.container_pool.shutdown()

    @pytest.mark.asyncio
    async def test_webhook_handler_allows_authorized_user(self):
        """Test that webhook handler allows authorized users for Claude dispatch."""
        from devs_webhook.config import get_config

        with patch.dict('os.environ', {
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_MENTIONED_USER': 'botuser',
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob',
            'ALLOWED_ORGS': 'testorg',
            'DEV_MODE': 'true'
        }):
            # Clear the config cache inside patch context so new config gets patched env
            get_config.cache_clear()
            handler = WebhookHandler()
            try:
                # Mock ensure_repo_config to avoid actual repo cloning
                from devs_common.devs_config import DevsOptions
                handler.container_pool.ensure_repo_config = AsyncMock(return_value=DevsOptions())

                # Create a mock event from authorized user
                headers = {'x-github-event': 'issues'}
                payload = json.dumps({
                    'action': 'opened',
                    'repository': {
                        'id': 1,
                        'name': 'testrepo',
                        'full_name': 'testorg/testrepo',
                        'owner': {
                            'login': 'testorg',
                            'id': 1,
                            'avatar_url': 'http://example.com',
                            'html_url': 'http://example.com'
                        },
                        'html_url': 'http://example.com',
                        'clone_url': 'http://example.com',
                        'ssh_url': 'http://example.com',
                        'default_branch': 'main'
                    },
                    'sender': {
                        'login': 'alice',  # In authorized list
                        'id': 123,
                        'avatar_url': 'http://example.com',
                        'html_url': 'http://example.com'
                    },
                    'issue': {
                        'id': 1,
                        'number': 1,
                        'title': 'Test issue',
                        'body': '@botuser please help',
                        'state': 'open',
                        'user': {
                            'login': 'alice',
                            'id': 123,
                            'avatar_url': 'http://example.com',
                            'html_url': 'http://example.com'
                        },
                        'html_url': 'http://example.com',
                        'created_at': '2024-01-01T00:00:00Z',
                        'updated_at': '2024-01-01T00:00:00Z'
                    }
                }).encode()

                # Mock the container pool to track if task was queued
                handler.container_pool.queue_task = AsyncMock(return_value=True)

                # Process the webhook
                await handler.process_webhook(headers, payload, 'test-delivery-id')

                # Task SHOULD have been queued for authorized user
                handler.container_pool.queue_task.assert_called_once()
            finally:
                # Clean up async workers
                await handler.container_pool.shutdown()

    @pytest.mark.asyncio
    async def test_status_includes_authorized_users(self):
        """Test that status endpoint includes authorized trigger users."""
        from devs_webhook.config import get_config

        with patch.dict('os.environ', {
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_MENTIONED_USER': 'botuser',
            'AUTHORIZED_TRIGGER_USERS': 'alice,bob,charlie',
            'AUTHORIZED_CI_TRIGGER_USERS': 'alice,bob,charlie,botuser',
            'DEV_MODE': 'true'
        }):
            # Clear the config cache inside patch context so new config gets patched env
            get_config.cache_clear()
            handler = WebhookHandler()
            try:
                # Mock container pool status with an async mock
                handler.container_pool.get_status = AsyncMock(return_value={})

                status = await handler.get_status()

                assert 'authorized_trigger_users' in status
                assert status['authorized_trigger_users'] == ['alice', 'bob', 'charlie']
                assert 'authorized_ci_trigger_users' in status
                assert status['authorized_ci_trigger_users'] == ['alice', 'bob', 'charlie', 'botuser']
            finally:
                # Clean up async workers
                await handler.container_pool.shutdown()