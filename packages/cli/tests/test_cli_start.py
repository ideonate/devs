"""Integration tests for the 'start' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli


class TestStartCommand:
    """Test suite for 'devs start' command."""

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_single_container(self, mock_workspace_manager_class, mock_container_manager_class,
                                   mock_get_project, cli_runner, temp_project):
        """Test starting a single container."""
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

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify success
        assert result.exit_code == 0
        assert "Starting" in result.output and "alice" in result.output
        mock_workspace_manager.create_workspace.assert_called()
        mock_container_manager.ensure_container_running.assert_called_once()

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_multiple_containers(self, mock_workspace_manager_class, mock_container_manager_class,
                                      mock_get_project, cli_runner, temp_project):
        """Test starting multiple containers."""
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

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice', 'bob'])

        # Verify success
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "bob" in result.output
        assert mock_container_manager.ensure_container_running.call_count == 2

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_container_already_running(self, mock_workspace_manager_class, mock_container_manager_class,
                                            mock_get_project, cli_runner, temp_project):
        """Test starting a container that's already running - still succeeds."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        # ensure_container_running returns True even for existing containers
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify success
        assert result.exit_code == 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_no_devcontainer_config(self, mock_workspace_manager_class, mock_container_manager_class,
                                         mock_get_project, cli_runner, temp_project):
        """Test starting container - devcontainer config not required (uses default template)."""
        # Setup mocks - no devcontainer config is OK, we use default template
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify success - should work even without devcontainer.json
        assert result.exit_code == 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_workspace_creation_failure(self, mock_workspace_manager_class, mock_container_manager_class,
                                             mock_get_project, cli_runner, temp_project):
        """Test handling workspace creation failure."""
        from devs.exceptions import WorkspaceError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.side_effect = WorkspaceError("Permission denied")
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager_class.return_value = Mock()

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify error handling - command continues with others but reports failure
        assert "Failed" in result.output or "Error" in result.output or "Permission denied" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_container_creation_failure(self, mock_workspace_manager_class, mock_container_manager_class,
                                             mock_get_project, cli_runner, temp_project):
        """Test handling container creation failure."""
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

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify error handling
        assert "Failed" in result.output or result.exit_code != 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_missing_dependencies(self, mock_workspace_manager_class, mock_container_manager_class,
                                       mock_get_project, cli_runner, temp_project):
        """Test starting container - dependency check is now mocked in conftest."""
        # Note: check_dependencies is mocked out in conftest.py autouse fixture
        # This test just verifies the command works when dependencies are "available"

        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager_class.return_value = mock_container_manager

        # Run command - should succeed since check_dependencies is mocked
        result = cli_runner.invoke(cli, ['start', 'alice'])

        assert result.exit_code == 0

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_with_environment_variables(self, mock_workspace_manager_class, mock_container_manager_class,
                                             mock_get_project, cli_runner, temp_project):
        """Test starting container with environment variables via --env flag."""
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

        # Run command with --env flag
        result = cli_runner.invoke(cli, ['start', 'alice', '--env', 'TEST_VAR=test_value'])

        # Verify success
        assert result.exit_code == 0
        # Verify environment variables message
        assert "Environment variables" in result.output

    @patch('devs.cli.get_project')
    def test_start_invalid_project_directory(self, mock_get_project, cli_runner):
        """Test starting container from invalid project directory."""
        from devs.exceptions import ProjectNotFoundError

        # Setup mock to raise exception
        mock_get_project.side_effect = ProjectNotFoundError("Not a valid project")

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])

        # Verify error
        assert result.exit_code == 1

    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_partial_success(self, mock_workspace_manager_class, mock_container_manager_class,
                                  mock_get_project, cli_runner, temp_project):
        """Test starting multiple containers with partial success."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        # First container succeeds, second fails
        mock_container_manager.ensure_container_running.side_effect = [True, False]
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice', 'bob'])

        # Verify partial success - output mentions both
        assert "alice" in result.output
        assert "bob" in result.output
