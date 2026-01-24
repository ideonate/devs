"""Tests for cleanup_mode functionality."""

import asyncio
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from devs_webhook.core.container_pool import ContainerPool
from devs_webhook.config import WebhookConfig


@pytest.fixture
def mock_config_full_cleanup():
    """Create a mock configuration with full cleanup mode."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry"]
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    config.cleanup_mode = "full"
    config.should_remove_workspace_on_cleanup.return_value = True
    config.worker_logs_enabled = False
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


@pytest.fixture
def mock_config_stop_only_cleanup():
    """Create a mock configuration with stop_only cleanup mode."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry"]
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    config.cleanup_mode = "stop_only"
    config.should_remove_workspace_on_cleanup.return_value = False
    config.worker_logs_enabled = False
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


class TestCleanupModeConfig:
    """Tests for cleanup_mode configuration."""

    def test_config_default_cleanup_mode(self):
        """Test that default cleanup_mode is 'full'."""
        # Create a minimal config with required fields
        with patch.dict('os.environ', {
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_MENTIONED_USER': 'testuser',
            'ADMIN_PASSWORD': 'test-password',
        }):
            config = WebhookConfig()
            assert config.cleanup_mode == "full"

    def test_config_stop_only_cleanup_mode(self):
        """Test that cleanup_mode can be set to 'stop_only'."""
        with patch.dict('os.environ', {
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_MENTIONED_USER': 'testuser',
            'ADMIN_PASSWORD': 'test-password',
            'CLEANUP_MODE': 'stop_only',
        }):
            config = WebhookConfig()
            assert config.cleanup_mode == "stop_only"

    def test_config_invalid_cleanup_mode(self):
        """Test that invalid cleanup_mode raises an error."""
        with patch.dict('os.environ', {
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_MENTIONED_USER': 'testuser',
            'ADMIN_PASSWORD': 'test-password',
            'CLEANUP_MODE': 'invalid',
        }):
            with pytest.raises(ValueError, match="cleanup_mode must be 'full' or 'stop_only'"):
                WebhookConfig()

    def test_should_remove_workspace_on_cleanup_full(self):
        """Test that should_remove_workspace_on_cleanup returns True for 'full' mode."""
        with patch.dict('os.environ', {
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_MENTIONED_USER': 'testuser',
            'ADMIN_PASSWORD': 'test-password',
            'CLEANUP_MODE': 'full',
        }):
            config = WebhookConfig()
            assert config.should_remove_workspace_on_cleanup() is True

    def test_should_remove_workspace_on_cleanup_stop_only(self):
        """Test that should_remove_workspace_on_cleanup returns False for 'stop_only' mode."""
        with patch.dict('os.environ', {
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_WEBHOOK_SECRET': 'test-secret',
            'GITHUB_MENTIONED_USER': 'testuser',
            'ADMIN_PASSWORD': 'test-password',
            'CLEANUP_MODE': 'stop_only',
        }):
            config = WebhookConfig()
            assert config.should_remove_workspace_on_cleanup() is False


class TestCleanupModeContainerPool:
    """Tests for cleanup_mode in ContainerPool."""

    @pytest.mark.asyncio
    async def test_status_includes_cleanup_mode_full(self, mock_config_full_cleanup):
        """Test that status endpoint includes cleanup_mode for full mode."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_full_cleanup):
            pool = ContainerPool()

            # Cancel workers to avoid background task issues
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            status = await pool.get_status()

            assert "cleanup_settings" in status
            assert "cleanup_mode" in status["cleanup_settings"]
            assert status["cleanup_settings"]["cleanup_mode"] == "full"

    @pytest.mark.asyncio
    async def test_status_includes_cleanup_mode_stop_only(self, mock_config_stop_only_cleanup):
        """Test that status endpoint includes cleanup_mode for stop_only mode."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_only_cleanup):
            pool = ContainerPool()

            # Cancel workers
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            status = await pool.get_status()

            assert status["cleanup_settings"]["cleanup_mode"] == "stop_only"

    @pytest.mark.asyncio
    async def test_cleanup_removes_workspace_in_full_mode(self, mock_config_full_cleanup):
        """Test that _cleanup_container removes workspace in full mode."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_full_cleanup):
            pool = ContainerPool()

            # Cancel workers
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            # Mock the managers
            mock_container_manager = MagicMock()
            mock_container_manager.stop_container.return_value = True
            mock_workspace_manager = MagicMock()
            mock_workspace_manager.remove_workspace.return_value = True

            with patch('devs_webhook.core.container_pool.ContainerManager', return_value=mock_container_manager), \
                 patch('devs_webhook.core.container_pool.WorkspaceManager', return_value=mock_workspace_manager), \
                 patch('devs_webhook.core.container_pool.Project'):

                await pool._cleanup_container("eamonn", Path("/tmp/test-repo"))

                # Verify container was stopped
                mock_container_manager.stop_container.assert_called_once_with("eamonn")
                # Verify workspace was removed
                mock_workspace_manager.remove_workspace.assert_called_once_with("eamonn")

    @pytest.mark.asyncio
    async def test_cleanup_keeps_workspace_in_stop_only_mode(self, mock_config_stop_only_cleanup):
        """Test that _cleanup_container keeps workspace in stop_only mode."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_only_cleanup):
            pool = ContainerPool()

            # Cancel workers
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            # Mock the managers
            mock_container_manager = MagicMock()
            mock_container_manager.stop_container.return_value = True
            mock_workspace_manager = MagicMock()
            mock_workspace_manager.get_workspace_path.return_value = Path("/tmp/workspace/eamonn")

            with patch('devs_webhook.core.container_pool.ContainerManager', return_value=mock_container_manager), \
                 patch('devs_webhook.core.container_pool.WorkspaceManager', return_value=mock_workspace_manager), \
                 patch('devs_webhook.core.container_pool.Project'):

                await pool._cleanup_container("eamonn", Path("/tmp/test-repo"))

                # Verify container was stopped
                mock_container_manager.stop_container.assert_called_once_with("eamonn")
                # Verify workspace was NOT removed
                mock_workspace_manager.remove_workspace.assert_not_called()
                # Verify get_workspace_path was called for logging
                mock_workspace_manager.get_workspace_path.assert_called_once_with("eamonn")

    @pytest.mark.asyncio
    async def test_stop_only_mode_preserves_workspace_for_reuse(self, mock_config_stop_only_cleanup):
        """Test that stop_only mode allows workspace reuse for same repo."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_only_cleanup):
            pool = ContainerPool()

            # Cancel workers
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            dev_name = "eamonn"
            repo_path = Path("/tmp/test-repo")

            # Mock the managers
            mock_container_manager = MagicMock()
            mock_container_manager.stop_container.return_value = True
            mock_workspace_manager = MagicMock()
            mock_workspace_manager.get_workspace_path.return_value = Path("/tmp/workspace/eamonn")

            with patch('devs_webhook.core.container_pool.ContainerManager', return_value=mock_container_manager), \
                 patch('devs_webhook.core.container_pool.WorkspaceManager', return_value=mock_workspace_manager), \
                 patch('devs_webhook.core.container_pool.Project'):

                # First cleanup
                await pool._cleanup_container(dev_name, repo_path)

                # Verify container stopped but workspace kept
                assert mock_container_manager.stop_container.call_count == 1
                assert mock_workspace_manager.remove_workspace.call_count == 0

                # Reset mocks for second cleanup
                mock_container_manager.reset_mock()
                mock_workspace_manager.reset_mock()

                # Second cleanup (simulating another task on same container)
                await pool._cleanup_container(dev_name, repo_path)

                # Again, container stopped but workspace still kept
                assert mock_container_manager.stop_container.call_count == 1
                assert mock_workspace_manager.remove_workspace.call_count == 0
