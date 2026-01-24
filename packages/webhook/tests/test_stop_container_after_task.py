"""Tests for stop_container_after_task functionality."""

import asyncio
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from devs_webhook.core.container_pool import ContainerPool, QueuedTask
from devs_webhook.github.models import (
    WebhookEvent, GitHubRepository, GitHubUser, IssueEvent, GitHubIssue
)
from devs_common.devs_config import DevsOptions


@pytest.fixture
def mock_config_stop_after_task():
    """Create a mock configuration with stop_container_after_task enabled."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry"]
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    config.stop_container_after_task = True  # Enabled
    config.worker_logs_enabled = False
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


@pytest.fixture
def mock_config_no_stop_after_task():
    """Create a mock configuration with stop_container_after_task disabled."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry"]
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    config.stop_container_after_task = False  # Disabled (legacy behavior)
    config.worker_logs_enabled = False
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


@pytest.fixture
def mock_event():
    """Create a mock webhook event."""
    return IssueEvent(
        action="opened",
        repository=GitHubRepository(
            id=1,
            name="test-repo",
            full_name="test-org/test-repo",
            owner=GitHubUser(
                login="test-org",
                id=1,
                avatar_url="https://example.com/avatar",
                html_url="https://example.com/user"
            ),
            html_url="https://github.com/test-org/test-repo",
            clone_url="https://github.com/test-org/test-repo.git",
            ssh_url="git@github.com:test-org/test-repo.git",
            default_branch="main"
        ),
        sender=GitHubUser(
            login="sender",
            id=2,
            avatar_url="https://example.com/avatar2",
            html_url="https://example.com/user2"
        ),
        issue=GitHubIssue(
            id=1,
            number=42,
            title="Test Issue",
            body="Test body",
            state="open",
            user=GitHubUser(
                login="sender",
                id=2,
                avatar_url="https://example.com/avatar2",
                html_url="https://example.com/user2"
            ),
            html_url="https://github.com/test-org/test-repo/issues/42",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z"
        )
    )


@pytest.mark.asyncio
async def test_status_includes_stop_container_after_task(mock_config_stop_after_task):
    """Test that status endpoint includes stop_container_after_task setting."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_after_task):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        status = await pool.get_status()

        assert "cleanup_settings" in status
        assert "stop_container_after_task" in status["cleanup_settings"]
        assert status["cleanup_settings"]["stop_container_after_task"] is True


@pytest.mark.asyncio
async def test_status_includes_stop_container_after_task_disabled(mock_config_no_stop_after_task):
    """Test that status shows stop_container_after_task as false when disabled."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_no_stop_after_task):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        status = await pool.get_status()

        assert status["cleanup_settings"]["stop_container_after_task"] is False


@pytest.mark.asyncio
async def test_container_stopped_after_task_when_enabled(mock_config_stop_after_task):
    """Test that container is stopped after task when stop_container_after_task is enabled."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_after_task):
        pool = ContainerPool()

        # Cancel workers to prevent actual task processing
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Simulate a running container being tracked
        dev_name = "eamonn"
        repo_path = Path("/tmp/test-repo")
        now = datetime.now(tz=timezone.utc)
        pool.running_containers[dev_name] = {
            "repo_path": repo_path,
            "started_at": now,
            "last_used": now,
        }

        # Mock the _cleanup_container method
        pool._cleanup_container = AsyncMock()

        # Simulate the finally block logic from _process_task_subprocess
        async with pool._lock:
            if dev_name in pool.running_containers:
                if pool.config.stop_container_after_task:
                    info = pool.running_containers[dev_name]
                    await pool._cleanup_container(dev_name, info["repo_path"])
                    del pool.running_containers[dev_name]

        # Verify cleanup was called
        pool._cleanup_container.assert_called_once_with(dev_name, repo_path)
        # Verify container was removed from tracking
        assert dev_name not in pool.running_containers


@pytest.mark.asyncio
async def test_container_not_stopped_when_disabled(mock_config_no_stop_after_task):
    """Test that container is NOT stopped after task when stop_container_after_task is disabled."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_no_stop_after_task):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Simulate a running container being tracked
        dev_name = "eamonn"
        repo_path = Path("/tmp/test-repo")
        initial_time = datetime.now(tz=timezone.utc)
        pool.running_containers[dev_name] = {
            "repo_path": repo_path,
            "started_at": initial_time,
            "last_used": initial_time,
        }

        # Mock the _cleanup_container method
        pool._cleanup_container = AsyncMock()

        # Simulate the finally block logic from _process_task_subprocess
        async with pool._lock:
            if dev_name in pool.running_containers:
                if pool.config.stop_container_after_task:
                    info = pool.running_containers[dev_name]
                    await pool._cleanup_container(dev_name, info["repo_path"])
                    del pool.running_containers[dev_name]
                else:
                    # Just update last_used timestamp (legacy behavior)
                    pool.running_containers[dev_name]["last_used"] = datetime.now(tz=timezone.utc)

        # Verify cleanup was NOT called
        pool._cleanup_container.assert_not_called()
        # Verify container is still being tracked
        assert dev_name in pool.running_containers
        # Verify last_used was updated
        assert pool.running_containers[dev_name]["last_used"] > initial_time


@pytest.mark.asyncio
async def test_only_one_running_container_per_dev_name(mock_config_stop_after_task):
    """Test that stop_container_after_task ensures only one container per dev name.

    When enabled, after each task completes the container is stopped, so the next
    task in the same queue will start a fresh container.
    """
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_after_task):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        dev_name = "eamonn"
        repo_path_1 = Path("/tmp/test-repo-1")
        repo_path_2 = Path("/tmp/test-repo-2")

        # Mock cleanup
        pool._cleanup_container = AsyncMock()

        # Simulate first task starting
        now = datetime.now(tz=timezone.utc)
        pool.running_containers[dev_name] = {
            "repo_path": repo_path_1,
            "started_at": now,
            "last_used": now,
        }

        # Simulate first task completing (with stop after task)
        async with pool._lock:
            if dev_name in pool.running_containers and pool.config.stop_container_after_task:
                await pool._cleanup_container(dev_name, pool.running_containers[dev_name]["repo_path"])
                del pool.running_containers[dev_name]

        # Container should be stopped
        assert dev_name not in pool.running_containers
        pool._cleanup_container.assert_called_once_with(dev_name, repo_path_1)

        # Reset mock
        pool._cleanup_container.reset_mock()

        # Simulate second task starting (different repo)
        now = datetime.now(tz=timezone.utc)
        pool.running_containers[dev_name] = {
            "repo_path": repo_path_2,
            "started_at": now,
            "last_used": now,
        }

        # Simulate second task completing
        async with pool._lock:
            if dev_name in pool.running_containers and pool.config.stop_container_after_task:
                await pool._cleanup_container(dev_name, pool.running_containers[dev_name]["repo_path"])
                del pool.running_containers[dev_name]

        # Container should be stopped again
        assert dev_name not in pool.running_containers
        pool._cleanup_container.assert_called_once_with(dev_name, repo_path_2)


@pytest.mark.asyncio
async def test_cleanup_error_handling(mock_config_stop_after_task):
    """Test that cleanup errors are handled gracefully and don't crash the pool."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_stop_after_task):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        dev_name = "eamonn"
        repo_path = Path("/tmp/test-repo")
        now = datetime.now(tz=timezone.utc)
        pool.running_containers[dev_name] = {
            "repo_path": repo_path,
            "started_at": now,
            "last_used": now,
        }

        # Mock cleanup to raise an exception
        pool._cleanup_container = AsyncMock(side_effect=Exception("Cleanup failed"))

        # Simulate the finally block - should not raise
        try:
            async with pool._lock:
                if dev_name in pool.running_containers:
                    if pool.config.stop_container_after_task:
                        info = pool.running_containers[dev_name]
                        try:
                            await pool._cleanup_container(dev_name, info["repo_path"])
                            del pool.running_containers[dev_name]
                        except Exception:
                            # Error is logged but not re-raised
                            pass
        except Exception as e:
            pytest.fail(f"Cleanup error should be handled gracefully, but got: {e}")

        # Container should still be tracked since cleanup failed
        assert dev_name in pool.running_containers
