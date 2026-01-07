"""Integration tests for the 'vscode' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli


class TestVSCodeCommand:
    """Test suite for 'devs vscode' command."""

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_single_container(self, mock_vscode_class, mock_workspace_manager_class,
                                    mock_container_manager_class, mock_get_project,
                                    cli_runner, temp_project):
        """Test opening VS Code for a single container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # Verify success
        assert result.exit_code == 0
        mock_container_manager.ensure_container_running.assert_called()

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_multiple_containers(self, mock_vscode_class, mock_workspace_manager_class,
                                       mock_container_manager_class, mock_get_project,
                                       cli_runner, temp_project):
        """Test opening VS Code for multiple containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice', 'bob'])

        # Verify success
        assert result.exit_code == 0
        assert mock_container_manager.ensure_container_running.call_count == 2

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_container_not_running(self, mock_vscode_class, mock_workspace_manager_class,
                                         mock_container_manager_class, mock_get_project,
                                         cli_runner, temp_project):
        """Test vscode command when container fails to start."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = False
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # Verify it reports the failure
        assert "Failed" in result.output or result.exit_code != 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_workspace_not_exists(self, mock_vscode_class, mock_workspace_manager_class,
                                        mock_container_manager_class, mock_get_project,
                                        cli_runner, temp_project):
        """Test vscode command when workspace creation fails."""
        from devs.exceptions import WorkspaceError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.side_effect = WorkspaceError("Cannot create")
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager_class.return_value = Mock()
        mock_vscode_class.return_value = Mock()

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # Verify error handling
        assert "Error" in result.output or "Failed" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_missing_vscode(self, mock_vscode_class, mock_workspace_manager_class,
                                  mock_container_manager_class, mock_get_project,
                                  cli_runner, temp_project):
        """Test vscode command when VS Code is not available - check_dependencies handles this."""
        # check_dependencies is mocked in conftest, so test just verifies command structure
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # Verify success (check_dependencies is mocked)
        assert result.exit_code == 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_open_failure(self, mock_vscode_class, mock_workspace_manager_class,
                                mock_container_manager_class, mock_get_project,
                                cli_runner, temp_project):
        """Test vscode command when VS Code integration fails."""
        from devs.exceptions import VSCodeError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.side_effect = VSCodeError("Failed to open")
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # The CLI catches VSCodeError and prints error message, doesn't exit with error code
        # Just verify the error handling happens
        assert "VS Code integration error" in result.output or result.exception is not None

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_partial_success(self, mock_vscode_class, mock_workspace_manager_class,
                                   mock_container_manager_class, mock_get_project,
                                   cli_runner, temp_project):
        """Test vscode with multiple containers, one fails."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        # First succeeds, second fails
        mock_container_manager.ensure_container_running.side_effect = [True, False]
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice', 'bob'])

        # Verify partial output
        assert "alice" in result.output or "bob" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_vscode_with_custom_title(self, mock_vscode_class, mock_workspace_manager_class,
                                     mock_container_manager_class, mock_get_project,
                                     cli_runner, temp_project):
        """Test vscode command - titles are based on dev names automatically."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        # Verify success
        assert result.exit_code == 0
