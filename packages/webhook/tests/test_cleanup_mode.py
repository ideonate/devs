"""Tests for container cleanup behavior.

The cleanup behavior always keeps the workspace for faster reuse -
only the container is stopped. This allows subsequent tasks on the
same repository to start faster without re-copying files.
"""

import asyncio
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from devs_webhook.core.container_pool import ContainerPool


@pytest.fixture
def mock_config():
    """Create a mock configuration for cleanup tests."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry"]
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    config.worker_logs_enabled = False
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


class TestCleanupContainerPool:
    """Tests for cleanup behavior in ContainerPool."""

    @pytest.mark.asyncio
    async def test_cleanup_stops_container_keeps_workspace(self, mock_config):
        """Test that _cleanup_container stops container but keeps workspace."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
            pool = ContainerPool()

            # Cancel workers to avoid background task issues
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
                # Verify workspace was NOT removed (kept for reuse)
                mock_workspace_manager.remove_workspace.assert_not_called()
                # Verify get_workspace_path was called for logging
                mock_workspace_manager.get_workspace_path.assert_called_once_with("eamonn")

    @pytest.mark.asyncio
    async def test_cleanup_preserves_workspace_for_reuse(self, mock_config):
        """Test that workspace is preserved across multiple cleanups for reuse."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
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

    @pytest.mark.asyncio
    async def test_status_includes_cleanup_settings(self, mock_config):
        """Test that status endpoint includes cleanup settings."""
        with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
            pool = ContainerPool()

            # Cancel workers to avoid background task issues
            for worker in pool.container_workers.values():
                worker.cancel()
            if pool.cleanup_worker:
                pool.cleanup_worker.cancel()

            status = await pool.get_status()

            assert "cleanup_settings" in status
            assert "idle_timeout_minutes" in status["cleanup_settings"]
            assert "max_age_hours" in status["cleanup_settings"]
            assert "check_interval_seconds" in status["cleanup_settings"]
            assert status["cleanup_settings"]["idle_timeout_minutes"] == 60
            assert status["cleanup_settings"]["max_age_hours"] == 10
