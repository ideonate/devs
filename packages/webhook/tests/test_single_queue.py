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
from devs_common.devs_config import DevsOptions

# Fixed test hash for mocking
TEST_CONFIG_HASH = "test-hash-123"


@pytest.fixture
def mock_config_hash():
    """Mock the config hash computation to return a consistent value."""
    with patch('devs_webhook.core.container_pool.compute_env_config_hash', return_value=TEST_CONFIG_HASH):
        yield


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
async def test_single_queue_repo_assignment(mock_config, mock_event, mock_config_hash):
    """Test that single-queue repos are assigned to the same container after detection."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
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
        
        # Simulate cached config that would be loaded after first clone
        # Cache format is (DevsOptions, config_hash)
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=True), "test-hash-123")
        
        # Simulate the registration that would happen after first clone
        # In real flow, this happens in _process_task_subprocess after _ensure_repository_cloned
        pool.single_queue_assignments["test-org/test-repo"] = "eamonn"
        
        # Queue first task - should go to the registered container
        success1 = await pool.queue_task(
            task_id="task-1",
            repo_name="test-org/test-repo",
            task_description="First task",
            event=mock_event
        )
        assert success1
        
        # Check that repo is registered for single-queue
        assert "test-org/test-repo" in pool.single_queue_assignments
        assigned_container = pool.single_queue_assignments["test-org/test-repo"]
        assert assigned_container == "eamonn"
        
        # Queue second task for same repo
        success2 = await pool.queue_task(
            task_id="task-2",
            repo_name="test-org/test-repo",
            task_description="Second task",
            event=mock_event
        )
        assert success2
        
        # Verify same container was used
        assert pool.single_queue_assignments["test-org/test-repo"] == assigned_container
        
        # Both tasks should be in the same queue (eamonn)
        assert pool.container_queues["eamonn"].qsize() == 2
        
        # Other queues should be empty
        for name in mock_config.get_container_pool_list():
            if name != "eamonn":
                assert pool.container_queues[name].qsize() == 0


@pytest.mark.asyncio
async def test_normal_repo_load_balancing(mock_config, mock_event):
    """Test that non-single-queue repos use normal load balancing."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
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
        
        # Simulate cached config for normal repo
        # Cache format is (DevsOptions, config_hash)
        pool.repo_configs["test-org/test-repo"] = (DevsOptions(single_queue=False), "test-hash-123")
        
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
        
        # Repo should NOT be in single_queue_assignments
        assert "test-org/test-repo" not in pool.single_queue_assignments
        
        # Task should have gone to harry or darren (less busy)
        assert pool.container_queues["harry"].qsize() == 1 or \
               pool.container_queues["darren"].qsize() == 1
        assert pool.container_queues["eamonn"].qsize() == 2  # Unchanged


@pytest.mark.asyncio
async def test_mixed_repos(mock_config, mock_event, mock_config_hash):
    """Test handling of both single-queue and normal repos simultaneously."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
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
        
        # Simulate cached configs for both repos
        # Cache format is (DevsOptions, config_hash)
        pool.repo_configs["test-org/single-repo"] = (DevsOptions(single_queue=True), "test-hash-123")
        pool.repo_configs["test-org/normal-repo"] = (DevsOptions(single_queue=False), "test-hash-456")
        
        # Simulate registration of single-queue repo (would happen after first clone)
        pool.single_queue_assignments["test-org/single-repo"] = "harry"
        
        # Queue tasks for single-queue repo
        await pool.queue_task("task-1", "test-org/single-repo", "Task 1", mock_event)
        await pool.queue_task("task-2", "test-org/single-repo", "Task 2", mock_event)
        
        # Queue tasks for normal repo
        await pool.queue_task("task-3", "test-org/normal-repo", "Task 3", mock_event)
        await pool.queue_task("task-4", "test-org/normal-repo", "Task 4", mock_event)
        
        # Single-queue repo should be assigned to one container
        assert "test-org/single-repo" in pool.single_queue_assignments
        single_container = pool.single_queue_assignments["test-org/single-repo"]
        assert pool.container_queues[single_container].qsize() >= 2
        
        # Normal repo should NOT be in single_queue_assignments
        assert "test-org/normal-repo" not in pool.single_queue_assignments
        
        # Total tasks should be 4
        total_tasks = sum(q.qsize() for q in pool.container_queues.values())
        assert total_tasks == 4


@pytest.mark.asyncio
async def test_single_queue_assignments_direct_manipulation(mock_config):
    """Test direct manipulation of single_queue_assignments."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
        pool = ContainerPool()
        
        # Cancel worker tasks
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Initially no single-queue repos
        assert len(pool.single_queue_assignments) == 0
        
        # Register a repo
        pool.single_queue_assignments["test-org/repo1"] = "eamonn"
        assert pool.single_queue_assignments["test-org/repo1"] == "eamonn"
        
        # Register another repo
        pool.single_queue_assignments["test-org/repo2"] = "harry"
        assert pool.single_queue_assignments["test-org/repo2"] == "harry"
        assert len(pool.single_queue_assignments) == 2
        
        # Try to register the same repo again - should change (direct assignment)
        pool.single_queue_assignments["test-org/repo1"] = "darren"
        assert pool.single_queue_assignments["test-org/repo1"] == "darren"  # Changed
        assert len(pool.single_queue_assignments) == 2


@pytest.mark.asyncio
async def test_status_includes_single_queue_repos(mock_config):
    """Test that status endpoint includes single_queue_assignments information."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
        pool = ContainerPool()
        
        # Cancel worker tasks
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Manually add some single-queue repos
        pool.single_queue_assignments = {
            "test-org/repo1": "eamonn",
            "test-org/repo2": "harry"
        }
        
        status = await pool.get_status()
        
        assert "single_queue_assignments" in status
        assert status["single_queue_assignments"] == {
            "test-org/repo1": "eamonn",
            "test-org/repo2": "harry"
        }


@pytest.mark.asyncio
async def test_remove_single_queue_when_devs_yml_changes(mock_config, mock_event):
    """Test that repos are removed from single_queue when DEVS.yml no longer has single_queue=true."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
        pool = ContainerPool()
        
        # Cancel worker tasks to prevent actual processing
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        # Initially register a repo as single-queue
        pool.single_queue_assignments["test-org/test-repo"] = "eamonn"
        assert "test-org/test-repo" in pool.single_queue_assignments
        assert pool.single_queue_assignments["test-org/test-repo"] == "eamonn"
        
        # Create repository directory with DEVS.yml that has single_queue: false
        repo_path = mock_config.repo_cache_dir / "test-org-test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        devs_yml = repo_path / "DEVS.yml"
        devs_yml.write_text(yaml.dump({"single_queue": False}))
        
        # Mock the _ensure_repository_cloned to return DevsOptions with single_queue=False
        with patch.object(pool, '_ensure_repository_cloned') as mock_ensure:
            mock_ensure.return_value = DevsOptions(single_queue=False)
            
            # Mock the subprocess execution to avoid actual Docker operations
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b'{"output": "success"}', b''))
                mock_subprocess.return_value = mock_process
                
                # Process a task - this should trigger the removal logic
                queued_task = QueuedTask(
                    task_id="task-1",
                    repo_name="test-org/test-repo",
                    task_description="Test task",
                    event=mock_event
                )
                
                await pool._process_task_subprocess("eamonn", queued_task)
                
                # Verify the repo was removed from single_queue_assignments
                assert "test-org/test-repo" not in pool.single_queue_assignments
        
        # Test with repo that was not previously in single_queue_assignments
        # Should not cause any errors
        with patch.object(pool, '_ensure_repository_cloned') as mock_ensure:
            mock_ensure.return_value = DevsOptions(single_queue=False)
            
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b'{"output": "success"}', b''))
                mock_subprocess.return_value = mock_process
                
                queued_task2 = QueuedTask(
                    task_id="task-2",
                    repo_name="test-org/other-repo",
                    task_description="Test task",
                    event=mock_event
                )
                
                await pool._process_task_subprocess("harry", queued_task2)
                
                # Should still not be in single_queue_assignments
                assert "test-org/other-repo" not in pool.single_queue_assignments


@pytest.mark.asyncio
async def test_single_queue_transitions(mock_config, mock_event):
    """Test transitions between single-queue and normal mode based on DEVS.yml changes."""
    with patch('devs_webhook.core.container_pool.get_config', return_value=mock_config):
        pool = ContainerPool()
        
        # Cancel worker tasks
        for name in mock_config.get_container_pool_list():
            pool.container_workers[name].cancel()
        pool.cleanup_worker.cancel()
        
        repo_name = "test-org/test-repo"
        
        # Step 1: Start with no single-queue registration
        assert repo_name not in pool.single_queue_assignments
        
        # Step 2: Process task with single_queue=true, should add to registry
        with patch.object(pool, '_ensure_repository_cloned') as mock_ensure:
            mock_ensure.return_value = DevsOptions(single_queue=True)
            
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b'{"output": "success"}', b''))
                mock_subprocess.return_value = mock_process
                
                queued_task = QueuedTask(
                    task_id="task-1",
                    repo_name=repo_name,
                    task_description="Enable single queue",
                    event=mock_event
                )
                
                await pool._process_task_subprocess("eamonn", queued_task)
                
                # Should now be registered
                assert repo_name in pool.single_queue_assignments
                assert pool.single_queue_assignments[repo_name] == "eamonn"
        
        # Step 3: Process task with single_queue=false, should remove from registry
        # Clear the cached config so it will be reloaded
        if repo_name in pool.repo_configs:
            del pool.repo_configs[repo_name]
            
        with patch.object(pool, '_ensure_repository_cloned') as mock_ensure:
            mock_ensure.return_value = DevsOptions(single_queue=False)
            
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b'{"output": "success"}', b''))
                mock_subprocess.return_value = mock_process
                
                queued_task = QueuedTask(
                    task_id="task-2",
                    repo_name=repo_name,
                    task_description="Disable single queue",
                    event=mock_event
                )
                
                await pool._process_task_subprocess("harry", queued_task)
                
                # Should now be removed
                assert repo_name not in pool.single_queue_assignments
        
        # Step 4: Re-enable single_queue, should add back with new container
        # Clear the cached config so it will be reloaded
        if repo_name in pool.repo_configs:
            del pool.repo_configs[repo_name]
            
        with patch.object(pool, '_ensure_repository_cloned') as mock_ensure:
            mock_ensure.return_value = DevsOptions(single_queue=True)
            
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b'{"output": "success"}', b''))
                mock_subprocess.return_value = mock_process
                
                queued_task = QueuedTask(
                    task_id="task-3",
                    repo_name=repo_name,
                    task_description="Re-enable single queue",
                    event=mock_event
                )
                
                await pool._process_task_subprocess("darren", queued_task)
                
                # Should be registered again with new container
                assert repo_name in pool.single_queue_assignments
                assert pool.single_queue_assignments[repo_name] == "darren"
