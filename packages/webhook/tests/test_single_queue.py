"""Tests for single-queue repository processing."""

import asyncio
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, mock_open

from devs_webhook.core.container_pool import ContainerPool, QueuedTask
from devs_webhook.github.models import (
    WebhookEvent, GitHubRepository, GitHubUser, IssueEvent, GitHubIssue
)


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.get_container_pool_list.return_value = ["eamonn", "harry", "darren"]
    config.github_token = "test-token-1234567890"  # Non-empty token
    config.container_timeout_minutes = 60
    # Create a real temp directory for repo_cache_dir
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
async def test_single_queue_repo_assignment(mock_config, mock_event):
    """Test that single-queue repos are assigned to the same container."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config), \
         patch('devs_webhook.core.container_pool.ClaudeDispatcher'):
        pool = ContainerPool()
        
        # Create repository directory with DEVS.yml
        repo_path = mock_config.repo_cache_dir / "test-org-test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        
        devs_yml = repo_path / "DEVS.yml"
        devs_yml.write_text(yaml.dump({"single_queue": True}))
        
        # Cancel worker tasks to prevent actual processing
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Queue first task
        success1 = await pool.queue_task(
            task_id="task-1",
            repo_name="test-org/test-repo",
            task_description="First task",
            event=mock_event
        )
        assert success1
        
        # Check that repo was assigned to a container
        assert "test-org/test-repo" in pool.single_queue_repos
        assigned_container = pool.single_queue_repos["test-org/test-repo"]
        assert assigned_container in mock_config.get_container_pool_list()
        
        # Queue second task for same repo
        success2 = await pool.queue_task(
            task_id="task-2",
            repo_name="test-org/test-repo",
            task_description="Second task",
            event=mock_event
        )
        assert success2
        
        # Verify same container was used
        assert pool.single_queue_repos["test-org/test-repo"] == assigned_container
        
        # Both tasks should be in the same queue
        assert pool.container_queues[assigned_container].qsize() == 2
        
        # Other queues should be empty
        for name in mock_config.get_container_pool_list():
            if name != assigned_container:
                assert pool.container_queues[name].qsize() == 0


@pytest.mark.asyncio
async def test_normal_repo_load_balancing(mock_config, mock_event):
    """Test that non-single-queue repos use normal load balancing."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config), \
         patch('devs_webhook.core.container_pool.ClaudeDispatcher'):
        pool = ContainerPool()
        
        # Create repository directory with DEVS.yml (single_queue: false)
        repo_path = mock_config.repo_cache_dir / "test-org-test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        
        devs_yml = repo_path / "DEVS.yml"
        devs_yml.write_text(yaml.dump({"single_queue": False}))
        
        # Cancel worker tasks to prevent actual processing
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Pre-fill one queue to test load balancing
        await pool.container_queues["eamonn"].put(MagicMock())
        await pool.container_queues["eamonn"].put(MagicMock())
        
        # Queue task - should go to a less busy queue
        success = await pool.queue_task(
            task_id="task-1",
            repo_name="test-org/test-repo",
            task_description="Test task",
            event=mock_event
        )
        assert success
        
        # Repo should NOT be in single_queue_repos
        assert "test-org/test-repo" not in pool.single_queue_repos
        
        # Task should have gone to harry or darren (less busy)
        assert pool.container_queues["harry"].qsize() == 1 or \
               pool.container_queues["darren"].qsize() == 1
        assert pool.container_queues["eamonn"].qsize() == 2  # Unchanged


@pytest.mark.asyncio
async def test_mixed_repos(mock_config, mock_event):
    """Test handling of both single-queue and normal repos simultaneously."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config), \
         patch('devs_webhook.core.container_pool.ClaudeDispatcher'):
        pool = ContainerPool()
        
        # Create two repos - one with single_queue, one without
        single_repo_path = mock_config.repo_cache_dir / "test-org-single-repo"
        single_repo_path.mkdir(parents=True, exist_ok=True)
        (single_repo_path / "DEVS.yml").write_text(yaml.dump({"single_queue": True}))
        
        normal_repo_path = mock_config.repo_cache_dir / "test-org-normal-repo"
        normal_repo_path.mkdir(parents=True, exist_ok=True)
        (normal_repo_path / "DEVS.yml").write_text(yaml.dump({"single_queue": False}))
        
        # Cancel worker tasks
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Queue tasks for single-queue repo
        await pool.queue_task("task-1", "test-org/single-repo", "Task 1", mock_event)
        await pool.queue_task("task-2", "test-org/single-repo", "Task 2", mock_event)
        
        # Queue tasks for normal repo
        await pool.queue_task("task-3", "test-org/normal-repo", "Task 3", mock_event)
        await pool.queue_task("task-4", "test-org/normal-repo", "Task 4", mock_event)
        
        # Single-queue repo should be assigned to one container
        assert "test-org/single-repo" in pool.single_queue_repos
        single_container = pool.single_queue_repos["test-org/single-repo"]
        assert pool.container_queues[single_container].qsize() >= 2
        
        # Normal repo should NOT be in single_queue_repos
        assert "test-org/normal-repo" not in pool.single_queue_repos
        
        # Total tasks should be 4
        total_tasks = sum(q.qsize() for q in pool.container_queues.values())
        assert total_tasks == 4


@pytest.mark.asyncio
async def test_status_includes_single_queue_repos(mock_config):
    """Test that status endpoint includes single_queue_repos information."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config), \
         patch('devs_webhook.core.container_pool.ClaudeDispatcher'):
        pool = ContainerPool()
        
        # Cancel worker tasks
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Manually add some single-queue repos
        pool.single_queue_repos = {
            "test-org/repo1": "eamonn",
            "test-org/repo2": "harry"
        }
        
        status = await pool.get_status()
        
        assert "single_queue_repos" in status
        assert status["single_queue_repos"] == {
            "test-org/repo1": "eamonn",
            "test-org/repo2": "harry"
        }