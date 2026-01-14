"""Tests for separate CI container pool functionality."""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from devs_webhook.core.container_pool import ContainerPool, QueuedTask
from devs_webhook.github.models import (
    WebhookEvent, GitHubRepository, GitHubUser, IssueEvent, GitHubIssue
)
from devs_common.devs_config import DevsOptions


@pytest.fixture
def mock_config_with_separate_ci_pool():
    """Create a mock configuration with separate CI container pool."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry"]
    config.get_ci_container_pool_list.return_value = ["ci1", "ci2"]
    config.has_separate_ci_pool.return_value = True
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


@pytest.fixture
def mock_config_without_separate_ci_pool():
    """Create a mock configuration without separate CI container pool (fallback)."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry", "darren"]
    config.get_ci_container_pool_list.return_value = ["eamonn", "harry", "darren"]  # Same as main
    config.has_separate_ci_pool.return_value = False
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
    temp_dir = tempfile.mkdtemp()
    config.repo_cache_dir = Path(temp_dir)
    return config


@pytest.fixture
def mock_config_with_overlapping_pools():
    """Create a mock configuration with overlapping CI and Claude pools."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry", "shared"]
    config.get_ci_container_pool_list.return_value = ["ci1", "shared", "ci2"]
    config.has_separate_ci_pool.return_value = True
    config.github_token = "test-token-1234567890"
    config.container_timeout_minutes = 60
    config.container_max_age_hours = 10
    config.cleanup_check_interval_seconds = 60
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
async def test_separate_ci_pool_creates_all_queues(mock_config_with_separate_ci_pool):
    """Test that when separate CI pool is configured, queues are created for all containers."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Should have queues for all containers from both pools
        expected_containers = {"eamonn", "harry", "ci1", "ci2"}
        assert set(pool.container_queues.keys()) == expected_containers


@pytest.mark.asyncio
async def test_claude_task_routes_to_claude_pool(mock_config_with_separate_ci_pool, mock_event):
    """Test that Claude tasks are routed to the Claude container pool."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Cache config for repo
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash")

        # Queue a Claude task
        success = await pool.queue_task(
            task_id="task-1",
            repo_name="test-org/test-repo",
            task_description="Claude task",
            event=mock_event,
            task_type='claude'
        )
        assert success

        # Task should be in one of the Claude pool containers
        claude_queue_sizes = [
            pool.container_queues["eamonn"].qsize(),
            pool.container_queues["harry"].qsize()
        ]
        ci_queue_sizes = [
            pool.container_queues["ci1"].qsize(),
            pool.container_queues["ci2"].qsize()
        ]

        assert sum(claude_queue_sizes) == 1
        assert sum(ci_queue_sizes) == 0


@pytest.mark.asyncio
async def test_tests_task_routes_to_ci_pool(mock_config_with_separate_ci_pool, mock_event):
    """Test that test tasks are routed to the CI container pool."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Cache config for repo
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash")

        # Queue a test task
        success = await pool.queue_task(
            task_id="task-1",
            repo_name="test-org/test-repo",
            task_description="Test task",
            event=mock_event,
            task_type='tests'
        )
        assert success

        # Task should be in one of the CI pool containers
        claude_queue_sizes = [
            pool.container_queues["eamonn"].qsize(),
            pool.container_queues["harry"].qsize()
        ]
        ci_queue_sizes = [
            pool.container_queues["ci1"].qsize(),
            pool.container_queues["ci2"].qsize()
        ]

        assert sum(claude_queue_sizes) == 0
        assert sum(ci_queue_sizes) == 1


@pytest.mark.asyncio
async def test_without_separate_ci_pool_fallback(mock_config_without_separate_ci_pool, mock_event):
    """Test that without separate CI pool, tests use main pool."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_without_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Cache config for repo
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash")

        # Queue both Claude and test tasks
        await pool.queue_task("task-1", "test-org/test-repo", "Claude task", mock_event, task_type='claude')
        await pool.queue_task("task-2", "test-org/test-repo", "Test task", mock_event, task_type='tests')

        # Both tasks should be in the main pool (since there's no separate CI pool)
        total_tasks = sum(q.qsize() for q in pool.container_queues.values())
        assert total_tasks == 2


@pytest.mark.asyncio
async def test_overlapping_pools_routes_correctly(mock_config_with_overlapping_pools, mock_event):
    """Test that overlapping pools route tasks correctly to shared containers."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_overlapping_pools):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Should have queues for all unique containers
        expected_containers = {"eamonn", "harry", "shared", "ci1", "ci2"}
        assert set(pool.container_queues.keys()) == expected_containers

        # Cache config for repo
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash")

        # Queue Claude task
        await pool.queue_task("task-1", "test-org/test-repo", "Claude", mock_event, task_type='claude')

        # Claude task should be in eamonn, harry, or shared
        claude_pool_count = (
            pool.container_queues["eamonn"].qsize() +
            pool.container_queues["harry"].qsize() +
            pool.container_queues["shared"].qsize()
        )
        assert claude_pool_count == 1

        # Queue test task
        await pool.queue_task("task-2", "test-org/test-repo", "Test", mock_event, task_type='tests')

        # Test task should be in ci1, shared, or ci2
        ci_pool_count = (
            pool.container_queues["ci1"].qsize() +
            pool.container_queues["shared"].qsize() +
            pool.container_queues["ci2"].qsize()
        )
        # Note: shared might have been used by Claude task too, so could be 1 or 2
        assert ci_pool_count >= 1


@pytest.mark.asyncio
async def test_ci_pool_load_balancing(mock_config_with_separate_ci_pool, mock_event):
    """Test that CI pool uses load balancing across its containers."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Cache config for repo
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash")

        # Pre-fill ci1 queue
        await pool.container_queues["ci1"].put(MagicMock())
        await pool.container_queues["ci1"].put(MagicMock())

        # Queue a test task - should go to ci2 (less busy)
        await pool.queue_task("task-1", "test-org/test-repo", "Test", mock_event, task_type='tests')

        # ci2 should have the task since ci1 was pre-filled
        assert pool.container_queues["ci1"].qsize() == 2
        assert pool.container_queues["ci2"].qsize() == 1


@pytest.mark.asyncio
async def test_status_shows_separate_pools(mock_config_with_separate_ci_pool):
    """Test that status endpoint shows separate pool information."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        status = await pool.get_status()

        # Should show separate pools
        assert "claude_container_pool" in status
        assert "ci_container_pool" in status
        assert status["claude_container_pool"] == ["eamonn", "harry"]
        assert status["ci_container_pool"] == ["ci1", "ci2"]
        assert status["total_claude_containers"] == 2
        assert status["total_ci_containers"] == 2


@pytest.mark.asyncio
async def test_status_shows_single_pool_when_not_separate(mock_config_without_separate_ci_pool):
    """Test that status endpoint shows single pool when CI pool not configured."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_without_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        status = await pool.get_status()

        # Should show single pool
        assert "container_pool" in status
        assert "claude_container_pool" not in status
        assert "ci_container_pool" not in status
        assert status["container_pool"] == ["eamonn", "harry", "darren"]
        assert status["total_containers"] == 3


@pytest.mark.asyncio
async def test_get_pool_for_task_type(mock_config_with_separate_ci_pool):
    """Test the _get_pool_for_task_type helper method."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config_with_separate_ci_pool):
        pool = ContainerPool()

        # Cancel workers
        for worker in pool.container_workers.values():
            worker.cancel()
        if pool.cleanup_worker:
            pool.cleanup_worker.cancel()

        # Test task type routing
        assert pool._get_pool_for_task_type('claude') == ["eamonn", "harry"]
        assert pool._get_pool_for_task_type('tests') == ["ci1", "ci2"]
        # Unknown task type defaults to Claude pool
        assert pool._get_pool_for_task_type('unknown') == ["eamonn", "harry"]
