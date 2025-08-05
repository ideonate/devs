"""Integration tests for the 'clean' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestCleanCommand:
    """Test suite for 'devs clean' command."""
    
    @patch('devs.cli.Project')
    def test_clean_project_containers(self, mock_project_class, cli_runner, temp_project):
        """Test cleaning all containers for current project."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.clean_project_containers.return_value = ["alice", "bob"]
            mock_container_manager_class.return_value = mock_container_manager
            
            # Setup workspace manager mock
            mock_workspace_manager = Mock()
            mock_workspace_manager.clean_project_workspaces.return_value = ["alice", "bob"]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['clean', '--project'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Cleaning all resources for project test-org-test-repo" in result.output
            assert "✓ Removed containers: alice, bob" in result.output
            assert "✓ Removed workspaces: alice, bob" in result.output
            
            # Verify calls
            mock_container_manager.clean_project_containers.assert_called_once()
            mock_workspace_manager.clean_project_workspaces.assert_called_once()
    
    @patch('devs.cli.Project')
    def test_clean_all_containers(self, mock_project_class, cli_runner, temp_project):
        """Test cleaning all devs containers across all projects."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.clean_all_containers.return_value = [
                ("test-org-test-repo", "alice"),
                ("test-org-test-repo", "bob"),
                ("other-org-other-repo", "charlie")
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.list_all_workspaces.return_value = [
                ("test-org-test-repo", "alice"),
                ("test-org-test-repo", "bob"),
                ("other-org-other-repo", "charlie"),
                ("old-project", "david")  # Orphaned workspace
            ]
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command with --all flag
            result = cli_runner.invoke(cli, ['clean', '--all'], input='y\n')
            
            # Verify success
            assert result.exit_code == 0
            assert "This will remove ALL devs containers and workspaces" in result.output
            assert "✓ Removed 3 containers" in result.output
            assert "✓ Removed 4 workspaces" in result.output
            
            # Verify calls
            mock_container_manager.clean_all_containers.assert_called_once()
            assert mock_workspace_manager.remove_workspace.call_count == 4
    
    @patch('devs.cli.Project')
    def test_clean_unused_workspaces(self, mock_project_class, cli_runner, temp_project):
        """Test cleaning unused workspaces."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            # Only alice container is running
            mock_container_manager.list_all_containers.return_value = [
                MockContainer("/dev-test-org-test-repo-alice", labels={
                    "devs.project": "test-org-test-repo",
                    "devs.name": "alice"
                })
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            # Both alice and bob workspaces exist
            mock_workspace_manager.list_all_workspaces.return_value = [
                ("test-org-test-repo", "alice"),
                ("test-org-test-repo", "bob")
            ]
            mock_workspace_manager.clean_unused_workspaces.return_value = [
                ("test-org-test-repo", "bob")
            ]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['clean', '--unused'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Cleaning unused workspaces" in result.output
            assert "✓ Removed workspace: test-org-test-repo-bob" in result.output
            
            # Verify calls
            mock_container_manager.list_all_containers.assert_called_once()
            mock_workspace_manager.clean_unused_workspaces.assert_called_once()
    
    @patch('devs.cli.Project')
    def test_clean_no_unused_workspaces(self, mock_project_class, cli_runner, temp_project):
        """Test cleaning when no unused workspaces exist."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.list_all_containers.return_value = []
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.clean_unused_workspaces.return_value = []
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['clean', '--unused'])
            
            # Verify success
            assert result.exit_code == 0
            assert "No unused workspaces found" in result.output
    
    @patch('devs.cli.Project')
    def test_clean_specific_containers(self, mock_project_class, cli_runner, temp_project):
        """Test cleaning specific named containers."""
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
                MockContainer("/dev-test-org-test-repo-alice"),
                None  # bob doesn't exist
            ]
            mock_container_manager.stop_container.return_value = True
            mock_container_manager.remove_container.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.remove_workspace.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['clean', 'alice', 'bob'])
            
            # Verify output
            assert result.exit_code == 0
            assert "Cleaning specific development environments" in result.output
            assert "✓ Cleaned alice" in result.output
            assert "Environment 'bob' not found" in result.output
    
    @patch('devs.cli.Project')
    def test_clean_all_cancelled(self, mock_project_class, cli_runner, temp_project):
        """Test cancelling clean all operation."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        # Run command with --all flag but cancel
        result = cli_runner.invoke(cli, ['clean', '--all'], input='n\n')
        
        # Verify cancellation
        assert result.exit_code == 0
        assert "This will remove ALL devs containers and workspaces" in result.output
        assert "Operation cancelled" in result.output
    
    @patch('devs.cli.Project')
    def test_clean_with_errors(self, mock_project_class, cli_runner, temp_project):
        """Test clean command with errors during cleanup."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.clean_project_containers.side_effect = Exception("Docker error")
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.clean_project_workspaces.return_value = ["alice"]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['clean', '--project'])
            
            # Should handle error gracefully
            assert result.exit_code == 0
            assert "Failed to clean containers: Docker error" in result.output
            assert "✓ Removed workspaces: alice" in result.output
    
    @patch('devs.cli.Project')
    def test_clean_dry_run(self, mock_project_class, cli_runner, temp_project):
        """Test clean command with dry-run option."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.list_containers.return_value = [
                MockContainer("/dev-test-org-test-repo-alice"),
                MockContainer("/dev-test-org-test-repo-bob")
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.list_workspaces.return_value = ["alice", "bob", "charlie"]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command with --dry-run
            result = cli_runner.invoke(cli, ['clean', '--project', '--dry-run'])
            
            # Verify dry run output
            assert result.exit_code == 0
            assert "DRY RUN - No changes will be made" in result.output
            assert "Would remove containers: alice, bob" in result.output
            assert "Would remove workspaces: alice, bob, charlie" in result.output
            
            # Verify nothing was actually cleaned
            mock_container_manager.clean_project_containers.assert_not_called()
            mock_workspace_manager.clean_project_workspaces.assert_not_called()
    
    @patch('devs.cli.Project')
    def test_clean_no_args_shows_help(self, mock_project_class, cli_runner, temp_project):
        """Test clean command with no arguments shows help."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        # Run command with no options
        result = cli_runner.invoke(cli, ['clean'])
        
        # Should show help
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--project" in result.output
        assert "--all" in result.output
        assert "--unused" in result.output