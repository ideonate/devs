"""Tests for allowlist functionality."""

import json
import pytest
from unittest.mock import patch, AsyncMock
from devs_webhook.config import WebhookConfig, get_config
from devs_webhook.core.webhook_handler import WebhookHandler
from devs_webhook.github.parser import WebhookParser


class TestAllowlist:
    """Test allowlist functionality."""
    
    def test_config_parses_comma_separated_orgs(self):
        """Test that comma-separated org lists are parsed correctly."""
        with patch.dict('os.environ', {'ALLOWED_ORGS': 'org1,org2,org3'}):
            config = WebhookConfig()
            assert config.get_allowed_orgs_list() == ['org1', 'org2', 'org3']
    
    def test_config_parses_comma_separated_users(self):
        """Test that comma-separated user lists are parsed correctly."""
        with patch.dict('os.environ', {'ALLOWED_USERS': 'user1,user2,user3'}):
            config = WebhookConfig()
            assert config.get_allowed_users_list() == ['user1', 'user2', 'user3']
    
    def test_config_handles_empty_allowlist(self):
        """Test that empty allowlists default to empty lists."""
        config = WebhookConfig()
        assert config.get_allowed_orgs_list() == []
        assert config.get_allowed_users_list() == []
    
    def test_config_strips_whitespace(self):
        """Test that whitespace is stripped from allowlist entries."""
        with patch.dict('os.environ', {'ALLOWED_ORGS': ' org1 , org2 , org3 '}):
            config = WebhookConfig()
            assert config.get_allowed_orgs_list() == ['org1', 'org2', 'org3']
    
    def test_is_repository_allowed_with_empty_allowlist(self):
        """Test that empty allowlist allows all repositories."""
        config = WebhookConfig()
        assert config.is_repository_allowed('test/repo', 'test') is True
        assert config.is_repository_allowed('other/repo', 'other') is True
    
    def test_is_repository_allowed_with_org_allowlist(self):
        """Test repository allowlist with organizations."""
        with patch.dict('os.environ', {'ALLOWED_ORGS': 'allowed-org,another-org'}):
            config = WebhookConfig()
            
            # Allowed org
            assert config.is_repository_allowed('allowed-org/repo', 'allowed-org') is True
            assert config.is_repository_allowed('another-org/repo', 'another-org') is True
            
            # Not allowed org
            assert config.is_repository_allowed('blocked-org/repo', 'blocked-org') is False
    
    def test_is_repository_allowed_with_user_allowlist(self):
        """Test repository allowlist with individual users."""
        with patch.dict('os.environ', {'ALLOWED_USERS': 'allowed-user,another-user'}):
            config = WebhookConfig()
            
            # Allowed user
            assert config.is_repository_allowed('allowed-user/repo', 'allowed-user') is True
            assert config.is_repository_allowed('another-user/repo', 'another-user') is True
            
            # Not allowed user
            assert config.is_repository_allowed('blocked-user/repo', 'blocked-user') is False
    
    def test_is_repository_allowed_with_mixed_allowlist(self):
        """Test repository allowlist with both orgs and users."""
        with patch.dict('os.environ', {
            'ALLOWED_ORGS': 'allowed-org',
            'ALLOWED_USERS': 'allowed-user'
        }):
            config = WebhookConfig()
            
            # Allowed org
            assert config.is_repository_allowed('allowed-org/repo', 'allowed-org') is True
            
            # Allowed user
            assert config.is_repository_allowed('allowed-user/repo', 'allowed-user') is True
            
            # Not allowed
            assert config.is_repository_allowed('blocked/repo', 'blocked') is False
    
    def create_mock_issue_event(self, repo_owner='test', repo_name='repo', mentioned_user='testuser'):
        """Create a mock issue event for testing."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 1,
                "number": 123,
                "title": "Test issue",
                "body": f"Hey @{mentioned_user} can you help?",
                "state": "open",
                "user": {
                    "login": "reporter",
                    "id": 456,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/reporter"
                },
                "html_url": f"https://github.com/{repo_owner}/{repo_name}/issues/123",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            },
            "repository": {
                "id": 789,
                "name": repo_name,
                "full_name": f"{repo_owner}/{repo_name}",
                "owner": {
                    "login": repo_owner,
                    "id": 111,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": f"https://github.com/{repo_owner}"
                },
                "html_url": f"https://github.com/{repo_owner}/{repo_name}",
                "clone_url": f"https://github.com/{repo_owner}/{repo_name}.git",
                "ssh_url": f"git@github.com:{repo_owner}/{repo_name}.git",
                "default_branch": "main"
            },
            "sender": {
                "login": "reporter",
                "id": 456,
                "avatar_url": "https://github.com/avatar.jpg",
                "html_url": "https://github.com/reporter"
            }
        }
        
        headers = {"x-github-event": "issues"}
        payload_bytes = json.dumps(payload).encode()
        
        return WebhookParser.parse_webhook(headers, payload_bytes)
    
    @pytest.mark.asyncio
    async def test_webhook_handler_rejects_non_allowlisted_repo(self):
        """Test that webhook handler rejects events from non-allowlisted repositories."""
        # Mock environment with allowlist
        with patch.dict('os.environ', {
            'ALLOWED_ORGS': 'allowed-org',
            'GITHUB_WEBHOOK_SECRET': 'secret',
            'GITHUB_TOKEN': 'token',
            'GITHUB_MENTIONED_USER': 'testuser'
        }):
            # Clear the config cache inside the patch context so new config gets patched env
            get_config.cache_clear()
            handler = WebhookHandler()
            try:
                # Create event from non-allowlisted repo
                event = self.create_mock_issue_event(repo_owner='blocked-org')

                # Mock the container pool to avoid actual container operations
                mock_queue = AsyncMock(return_value=True)
                with patch.object(handler.container_pool, 'queue_task', mock_queue):
                    headers = {"x-github-event": "issues"}
                    payload = json.dumps({
                        "action": "opened",
                        "repository": {
                            "full_name": "blocked-org/repo",
                            "owner": {"login": "blocked-org"}
                        },
                        "issue": {"body": "@testuser help"},
                        "sender": {"login": "reporter"}
                    }).encode()

                    await handler.process_webhook(headers, payload, "test-delivery-id")

                    # Verify task was not queued
                    mock_queue.assert_not_called()
            finally:
                # Clean up async workers
                await handler.container_pool.shutdown()
    
    @pytest.mark.asyncio
    async def test_webhook_handler_allows_allowlisted_repo(self):
        """Test that webhook handler allows events from allowlisted repositories."""
        # Mock environment with allowlist
        with patch.dict('os.environ', {
            'ALLOWED_ORGS': 'allowed-org',
            'GITHUB_WEBHOOK_SECRET': 'secret',
            'GITHUB_TOKEN': 'token',
            'GITHUB_MENTIONED_USER': 'testuser'
        }):
            # Clear the config cache inside the patch context so new config gets patched env
            get_config.cache_clear()
            handler = WebhookHandler()
            try:
                # Mock the container pool methods to avoid actual operations
                from devs_common.devs_config import DevsOptions
                mock_queue = AsyncMock(return_value=True)
                mock_ensure_config = AsyncMock(return_value=DevsOptions())
                with patch.object(handler.container_pool, 'queue_task', mock_queue):
                    with patch.object(handler.container_pool, 'ensure_repo_config', mock_ensure_config):
                        headers = {"x-github-event": "issues"}
                        payload_data = {
                            "action": "opened",
                            "repository": {
                                "id": 789,
                                "name": "repo",
                                "full_name": "allowed-org/repo",
                                "owner": {
                                    "login": "allowed-org",
                                    "id": 111,
                                    "avatar_url": "https://github.com/avatar.jpg",
                                    "html_url": "https://github.com/allowed-org"
                                },
                                "html_url": "https://github.com/allowed-org/repo",
                                "clone_url": "https://github.com/allowed-org/repo.git",
                                "ssh_url": "git@github.com:allowed-org/repo.git",
                                "default_branch": "main"
                            },
                            "issue": {
                                "id": 1,
                                "number": 123,
                                "title": "Test issue",
                                "body": "@testuser help with this",
                                "state": "open",
                                "user": {
                                    "login": "reporter",
                                    "id": 456,
                                    "avatar_url": "https://github.com/avatar.jpg",
                                    "html_url": "https://github.com/reporter"
                                },
                                "html_url": "https://github.com/allowed-org/repo/issues/123",
                                "created_at": "2023-01-01T00:00:00Z",
                                "updated_at": "2023-01-01T00:00:00Z"
                            },
                            "sender": {
                                "login": "reporter",
                                "id": 456,
                                "avatar_url": "https://github.com/avatar.jpg",
                                "html_url": "https://github.com/reporter"
                            }
                        }
                        payload = json.dumps(payload_data).encode()

                        await handler.process_webhook(headers, payload, "test-delivery-id")

                        # Verify task was queued
                        mock_queue.assert_called_once()
            finally:
                # Clean up async workers
                await handler.container_pool.shutdown()