"""Comprehensive tests for ContainerManager class."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from devs_common.core.container import ContainerManager
from devs_common.core.project import Project
from devs_common.exceptions import ContainerError, DockerError
from tests.conftest import MockContainer


class TestContainerManager:
    """Test suite for ContainerManager class."""
    
    def test_init(self, mock_project):
        """Test ContainerManager initialization."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            
            manager = ContainerManager(mock_project)
            assert manager.project == mock_project
            assert manager.docker_client is not None
    
    def test_init_docker_not_available(self, mock_project):
        """Test ContainerManager initialization when Docker is not available."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker.from_env.side_effect = Exception("Docker not found")
            
            with pytest.raises(DockerError) as exc_info:
                ContainerManager(mock_project)
            
            assert "Failed to connect to Docker" in str(exc_info.value)
    
    def test_get_container_name(self, mock_container_manager):
        """Test container name generation."""
        name = mock_container_manager.get_container_name("alice")
        assert name == "dev-test-org-test-repo-alice"
    
    def test_list_containers(self, mock_container_manager, mock_containers):
        """Test listing containers for current project."""
        mock_container_manager.docker_client.containers.list.return_value = mock_containers
        
        containers = mock_container_manager.list_containers()
        
        # Should only return containers for the current project
        assert len(containers) == 2
        assert all(c.attrs["Config"]["Labels"]["devs.project"] == "test-org-test-repo" for c in containers)
        assert {c.attrs["Config"]["Labels"]["devs.name"] for c in containers} == {"alice", "bob"}
    
    def test_list_all_containers(self, mock_container_manager, mock_containers):
        """Test listing all devs containers."""
        mock_container_manager.docker_client.containers.list.return_value = mock_containers
        
        containers = mock_container_manager.list_all_containers()
        
        # Should return all containers with devs prefix
        assert len(containers) == 3
        assert all(c.name.startswith("dev-") for c in containers)
    
    def test_get_container_exists(self, mock_container_manager):
        """Test getting an existing container."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        container = mock_container_manager.get_container("alice")
        
        assert container == mock_container
        mock_container_manager.docker_client.containers.get.assert_called_once_with(
            "dev-test-org-test-repo-alice"
        )
    
    def test_get_container_not_found(self, mock_container_manager):
        """Test getting a non-existent container."""
        mock_container_manager.docker_client.containers.get.side_effect = Exception("Not found")
        
        container = mock_container_manager.get_container("alice")
        
        assert container is None
    
    def test_is_container_running_true(self, mock_container_manager):
        """Test checking if container is running (true case)."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        is_running = mock_container_manager.is_container_running("alice")
        
        assert is_running is True
    
    def test_is_container_running_false(self, mock_container_manager):
        """Test checking if container is running (false case)."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="exited")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        is_running = mock_container_manager.is_container_running("alice")
        
        assert is_running is False
    
    def test_is_container_running_not_found(self, mock_container_manager):
        """Test checking if container is running when container doesn't exist."""
        mock_container_manager.docker_client.containers.get.side_effect = Exception("Not found")
        
        is_running = mock_container_manager.is_container_running("alice")
        
        assert is_running is False
    
    @patch('subprocess.run')
    def test_build_or_update_image_success(self, mock_run, mock_container_manager, temp_project):
        """Test successful image build/update."""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        result = mock_container_manager.build_or_update_image("alice", temp_project)
        
        assert result is True
        mock_run.assert_called_once()
        
        # Check the command includes necessary components
        cmd = mock_run.call_args[0][0]
        assert "devcontainer" in cmd
        assert "build" in cmd
        assert str(temp_project) in cmd
    
    @patch('subprocess.run')
    def test_build_or_update_image_failure(self, mock_run, mock_container_manager, temp_project):
        """Test failed image build/update."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Build failed")
        
        with pytest.raises(ContainerError) as exc_info:
            mock_container_manager.build_or_update_image("alice", temp_project)
        
        assert "Failed to build/update image" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_create_container_success(self, mock_run, mock_container_manager, temp_project):
        """Test successful container creation."""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        # Mock that container doesn't exist initially
        mock_container_manager.get_container = Mock(return_value=None)
        
        result = mock_container_manager.create_container("alice", temp_project)
        
        assert result is True
        mock_run.assert_called_once()
        
        # Check the command includes necessary components
        cmd = mock_run.call_args[0][0]
        assert "devcontainer" in cmd
        assert "up" in cmd
        assert str(temp_project) in cmd
    
    @patch('subprocess.run')
    def test_create_container_already_exists(self, mock_run, mock_container_manager, temp_project):
        """Test container creation when container already exists."""
        # Mock that container exists
        mock_container = MockContainer("/dev-test-org-test-repo-alice")
        mock_container_manager.get_container = Mock(return_value=mock_container)
        
        result = mock_container_manager.create_container("alice", temp_project)
        
        assert result is True
        mock_run.assert_not_called()  # Should not try to create
    
    def test_stop_container_success(self, mock_container_manager):
        """Test successful container stop."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        result = mock_container_manager.stop_container("alice")
        
        assert result is True
        assert mock_container.status == "exited"  # Our mock changes status
    
    def test_stop_container_not_found(self, mock_container_manager):
        """Test stopping non-existent container."""
        mock_container_manager.docker_client.containers.get.side_effect = Exception("Not found")
        
        result = mock_container_manager.stop_container("alice")
        
        assert result is False
    
    def test_remove_container_success(self, mock_container_manager):
        """Test successful container removal."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="exited")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        result = mock_container_manager.remove_container("alice")
        
        assert result is True
    
    def test_remove_container_running(self, mock_container_manager):
        """Test removing a running container (should stop first)."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        result = mock_container_manager.remove_container("alice")
        
        assert result is True
        assert mock_container.status == "exited"  # Should have been stopped
    
    def test_exec_in_container_success(self, mock_container_manager):
        """Test successful command execution in container."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice")
        mock_container.exec_run = Mock(return_value=(0, b"Hello from container"))
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        exit_code, output = mock_container_manager.exec_in_container("alice", "echo 'Hello'")
        
        assert exit_code == 0
        assert output == "Hello from container"
        mock_container.exec_run.assert_called_once_with(
            "echo 'Hello'",
            tty=True,
            environment={}
        )
    
    def test_exec_in_container_with_env(self, mock_container_manager):
        """Test command execution with environment variables."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice")
        mock_container.exec_run = Mock(return_value=(0, b"Token: secret"))
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        env_vars = {"GH_TOKEN": "secret"}
        exit_code, output = mock_container_manager.exec_in_container(
            "alice", "echo $GH_TOKEN", env_vars=env_vars
        )
        
        assert exit_code == 0
        mock_container.exec_run.assert_called_once_with(
            "echo $GH_TOKEN",
            tty=True,
            environment=env_vars
        )
    
    def test_exec_in_container_not_found(self, mock_container_manager):
        """Test command execution in non-existent container."""
        mock_container_manager.docker_client.containers.get.side_effect = Exception("Not found")
        
        with pytest.raises(ContainerError) as exc_info:
            mock_container_manager.exec_in_container("alice", "echo 'Hello'")
        
        assert "Container 'alice' not found" in str(exc_info.value)
    
    def test_exec_in_container_not_running(self, mock_container_manager):
        """Test command execution in stopped container."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="exited")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        with pytest.raises(ContainerError) as exc_info:
            mock_container_manager.exec_in_container("alice", "echo 'Hello'")
        
        assert "Container 'alice' is not running" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_ensure_container_running_new_container(self, mock_run, mock_container_manager, temp_project):
        """Test ensuring container is running when it doesn't exist."""
        mock_run.return_value = Mock(returncode=0)
        
        # Container doesn't exist initially
        mock_container_manager.get_container = Mock(side_effect=[
            None,  # First check: doesn't exist
            MockContainer("/dev-test-org-test-repo-alice", status="running")  # After creation
        ])
        
        result = mock_container_manager.ensure_container_running("alice", temp_project)
        
        assert result is True
        assert mock_run.call_count == 2  # build and create
    
    def test_ensure_container_running_already_running(self, mock_container_manager, temp_project):
        """Test ensuring container is running when it's already running."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        mock_container_manager.get_container = Mock(return_value=mock_container)
        
        result = mock_container_manager.ensure_container_running("alice", temp_project)
        
        assert result is True
    
    @patch('subprocess.run')
    def test_ensure_container_running_stopped(self, mock_run, mock_container_manager, temp_project):
        """Test ensuring container is running when it's stopped."""
        mock_run.return_value = Mock(returncode=0)
        
        # Container exists but is stopped
        stopped_container = MockContainer("/dev-test-org-test-repo-alice", status="exited")
        running_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        
        mock_container_manager.get_container = Mock(side_effect=[
            stopped_container,  # First check: exists but stopped
            None,  # After removal
            running_container  # After recreation
        ])
        
        mock_container_manager.remove_container = Mock(return_value=True)
        
        result = mock_container_manager.ensure_container_running("alice", temp_project)
        
        assert result is True
        mock_container_manager.remove_container.assert_called_once_with("alice")
    
    def test_get_env_vars(self, mock_container_manager, monkeypatch):
        """Test environment variable collection."""
        monkeypatch.setenv("GH_TOKEN", "test-token")
        monkeypatch.setenv("CUSTOM_VAR", "custom-value")
        
        env_vars = mock_container_manager._get_env_vars("alice")
        
        assert env_vars["DEVCONTAINER_NAME"] == "alice"
        assert env_vars["GH_TOKEN"] == "test-token"
        assert "CUSTOM_VAR" in env_vars  # Should include all env vars
    
    def test_wait_for_container_health_healthy(self, mock_container_manager):
        """Test waiting for container to become healthy."""
        mock_container = MockContainer("/dev-test-org-test-repo-alice", status="running")
        mock_container_manager.docker_client.containers.get.return_value = mock_container
        
        result = mock_container_manager.wait_for_container_health("alice", timeout=5)
        
        assert result is True
    
    def test_wait_for_container_health_timeout(self, mock_container_manager):
        """Test waiting for container health with timeout."""
        # Container never becomes healthy
        mock_container_manager.get_container = Mock(return_value=None)
        
        result = mock_container_manager.wait_for_container_health("alice", timeout=0.1)
        
        assert result is False
    
    def test_clean_project_containers(self, mock_container_manager, mock_containers):
        """Test cleaning all containers for current project."""
        mock_container_manager.docker_client.containers.list.return_value = mock_containers[:2]  # alice and bob
        
        for container in mock_containers[:2]:
            container.stop = Mock()
            container.remove = Mock()
        
        removed = mock_container_manager.clean_project_containers()
        
        assert removed == ["alice", "bob"]
        for container in mock_containers[:2]:
            container.stop.assert_called_once()
            container.remove.assert_called_once()
    
    def test_clean_all_containers(self, mock_container_manager, mock_containers):
        """Test cleaning all devs containers."""
        mock_container_manager.docker_client.containers.list.return_value = mock_containers
        
        for container in mock_containers:
            container.stop = Mock()
            container.remove = Mock()
        
        removed = mock_container_manager.clean_all_containers()
        
        assert len(removed) == 3
        for container in mock_containers:
            container.stop.assert_called_once()
            container.remove.assert_called_once()