"""Integration tests for the 'stop' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestStopCommand:
    """Test suite for 'devs stop' command."""
    
    @patch('devs.cli.Project')
    def test_stop_single_container(self, mock_project_class, cli_runner, temp_project):
        """Test stopping a single container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = MockContainer(
                "/dev-test-org-test-repo-alice", "running"
            )
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            # Setup workspace manager mock
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Stopping development environment 'alice'" in result.output
            assert "✓ Stopped and removed container alice" in result.output
            assert "✓ Removed workspace for alice" in result.output
            assert "Successfully stopped: alice" in result.output
            
            # Verify calls
            mock_container_manager.stop_container.assert_called_once_with("alice")
            mock_container_manager.remove_container.assert_called_once_with("alice")
            mock_workspace_manager.remove_workspace.assert_called_once_with("alice")
    
    @patch('devs.cli.Project')
    def test_stop_multiple_containers(self, mock_project_class, cli_runner, temp_project):
        """Test stopping multiple containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.get_container.side_effect = [
                MockContainer("/dev-test-org-test-repo-alice", "running"),
                MockContainer("/dev-test-org-test-repo-bob", "running")
            ]
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice', 'bob'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Stopping development environment 'alice'" in result.output
            assert "Stopping development environment 'bob'" in result.output
            assert "Successfully stopped: alice, bob" in result.output
            
            # Verify calls
            assert mock_container_manager.stop_container.call_count == 2
            assert mock_container_manager.remove_container.call_count == 2
            assert mock_workspace_manager.remove_workspace.call_count == 2
    
    @patch('devs.cli.Project')
    def test_stop_container_not_found(self, mock_project_class, cli_runner, temp_project):
        """Test stopping a non-existent container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Container doesn't exist
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = None
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice'])
            
            # Verify handling
            assert result.exit_code == 0
            assert "Container 'alice' not found" in result.output
            assert "✓ Removed workspace for alice" in result.output
    
    @patch('devs.cli.Project')
    def test_stop_already_stopped_container(self, mock_project_class, cli_runner, temp_project):
        """Test stopping an already stopped container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Container exists but is already stopped
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = MockContainer(
                "/dev-test-org-test-repo-alice", "exited"
            )
            mock_container_manager.stop_container.return_value = True  # Already stopped
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            assert "✓ Stopped and removed container alice" in result.output
            assert "✓ Removed workspace for alice" in result.output
    
    @patch('devs.cli.Project')
    def test_stop_container_removal_failure(self, mock_project_class, cli_runner, temp_project):
        """Test handling container removal failure."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = MockContainer(
                "/dev-test-org-test-repo-alice", "running"
            )
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = False  # Removal fails
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice'])
            
            # Verify error handling
            assert result.exit_code == 1
            assert "Failed to remove container alice" in result.output
            # Workspace should still be removed
            assert "✓ Removed workspace for alice" in result.output
    
    @patch('devs.cli.Project')
    def test_stop_workspace_removal_failure(self, mock_project_class, cli_runner, temp_project):
        """Test handling workspace removal failure."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = MockContainer(
                "/dev-test-org-test-repo-alice", "running"
            )
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            # Workspace removal fails
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.side_effect = Exception("Permission denied")
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice'])
            
            # Verify error handling
            assert result.exit_code == 1
            assert "✓ Stopped and removed container alice" in result.output
            assert "Failed to remove workspace" in result.output
    
    @patch('devs.cli.Project')
    def test_stop_partial_success(self, mock_project_class, cli_runner, temp_project):
        """Test stopping multiple containers with partial success."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.get_container.side_effect = [
                MockContainer("/dev-test-org-test-repo-alice", "running"),
                MockContainer("/dev-test-org-test-repo-bob", "running")
            ]
            # First container stops successfully, second fails
            mock_container_manager.stop_container.side_effect = [True, False]
            mock_container_manager.remove_container.side_effect = [True, False]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['stop', 'alice', 'bob'])
            
            # Verify partial success
            assert result.exit_code == 1
            assert "Successfully stopped: alice" in result.output
            assert "Failed to stop: bob" in result.output
    
    @patch('devs.cli.Project')
    def test_stop_with_keep_workspace_flag(self, mock_project_class, cli_runner, temp_project):
        """Test stopping container while keeping workspace."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.get_container.return_value = MockContainer(
                "/dev-test-org-test-repo-alice", "running"
            )
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command with --keep-workspace flag
            result = cli_runner.invoke(cli, ['stop', 'alice', '--keep-workspace'])
            
            # Verify success
            assert result.exit_code == 0
            assert "✓ Stopped and removed container alice" in result.output
            assert "Keeping workspace for alice" in result.output
            
            # Verify workspace was not removed
            mock_workspace_manager.remove_workspace.assert_not_called()
    
    @patch('devs.cli.Project')
    def test_stop_all_containers(self, mock_project_class, cli_runner, temp_project, mock_containers):
        """Test stopping all containers for the project."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            # Return only containers for current project
            mock_container_manager.list_containers.return_value = mock_containers[:2]  # alice and bob
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command with --all flag
            result = cli_runner.invoke(cli, ['stop', '--all'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Stopping all containers for project test-org-test-repo" in result.output
            assert "✓ Stopped and removed container alice" in result.output
            assert "✓ Stopped and removed container bob" in result.output
            
            # Verify calls
            assert mock_container_manager.stop_container.call_count == 2
            assert mock_container_manager.remove_container.call_count == 2
            assert mock_workspace_manager.remove_workspace.call_count == 2