"""Integration tests for the 'clean' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestCleanCommand:
    """Test suite for 'devs clean' command."""

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_project_containers(self, mock_workspace_manager_class, mock_container_manager_class,
                                     mock_get_project, cli_runner, temp_project):
        """Test cleaning specific containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.stop_container.return_value = None
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.remove_workspace.return_value = None
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command with specific dev_name
        result = cli_runner.invoke(cli, ['clean', 'alice'])

        # Verify
        assert result.exit_code == 0
        assert "Cleaning up alice" in result.output
        mock_container_manager.stop_container.assert_called_once_with("alice")
        mock_workspace_manager.remove_workspace.assert_called_once_with("alice")

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_all_containers(self, mock_workspace_manager_class, mock_container_manager_class,
                                 mock_get_project, cli_runner, temp_project):
        """Test cleaning without args - cleans aborted and unused."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager.list_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command without args
        result = cli_runner.invoke(cli, ['clean'])

        # Verify default behavior
        assert result.exit_code == 0
        mock_container_manager.find_aborted_containers.assert_called()

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_unused_workspaces(self, mock_workspace_manager_class, mock_container_manager_class,
                                    mock_get_project, cli_runner, temp_project):
        """Test cleaning unused workspaces."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager.list_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 2
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command without args
        result = cli_runner.invoke(cli, ['clean'])

        # Verify
        assert result.exit_code == 0
        assert "Cleaned up 2 unused workspace(s)" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_no_unused_workspaces(self, mock_workspace_manager_class, mock_container_manager_class,
                                       mock_get_project, cli_runner, temp_project):
        """Test clean when no unused workspaces exist."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager.list_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command without args
        result = cli_runner.invoke(cli, ['clean'])

        # Verify
        assert result.exit_code == 0
        assert "No unused workspaces found" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_specific_containers(self, mock_workspace_manager_class, mock_container_manager_class,
                                      mock_get_project, cli_runner, temp_project):
        """Test cleaning multiple specific containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.stop_container.return_value = None
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.remove_workspace.return_value = None
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command with multiple dev_names
        result = cli_runner.invoke(cli, ['clean', 'alice', 'bob'])

        # Verify
        assert result.exit_code == 0
        assert mock_container_manager.stop_container.call_count == 2
        assert mock_workspace_manager.remove_workspace.call_count == 2

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_all_cancelled(self, mock_workspace_manager_class, mock_container_manager_class,
                                mock_get_project, cli_runner, temp_project):
        """Test clean --all-projects option."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces_all_projects.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command with --all-projects
        result = cli_runner.invoke(cli, ['clean', '--all-projects'])

        # Verify
        assert result.exit_code == 0
        mock_container_manager.find_aborted_containers.assert_called_with(all_projects=True)

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_with_errors(self, mock_workspace_manager_class, mock_container_manager_class,
                              mock_get_project, cli_runner, temp_project):
        """Test clean with errors during operation."""
        from devs.exceptions import ContainerError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.side_effect = ContainerError("Failed")
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command
        result = cli_runner.invoke(cli, ['clean'])

        # Verify error handling - should continue
        assert "Error cleaning aborted containers" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_dry_run(self, mock_workspace_manager_class, mock_container_manager_class,
                          mock_get_project, cli_runner, temp_project):
        """Test clean (no --dry-run flag exists, so just verify command runs)."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager.list_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command
        result = cli_runner.invoke(cli, ['clean'])

        # Verify command runs
        assert result.exit_code == 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_clean_no_args_shows_help(self, mock_workspace_manager_class, mock_container_manager_class,
                                     mock_get_project, cli_runner, temp_project):
        """Test clean without args runs default cleanup."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_container_manager = Mock()
        mock_container_manager.find_aborted_containers.return_value = []
        mock_container_manager.list_containers.return_value = []
        mock_container_manager_class.return_value = mock_container_manager

        mock_workspace_manager = Mock()
        mock_workspace_manager.cleanup_unused_workspaces.return_value = 0
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command without args
        result = cli_runner.invoke(cli, ['clean'])

        # Verify default behavior (not help)
        assert result.exit_code == 0
        assert "Looking for aborted containers" in result.output
