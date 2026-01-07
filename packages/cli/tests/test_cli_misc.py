"""Integration tests for miscellaneous CLI commands (list, status, shell, claude)."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestListCommand:
    """Test suite for 'devs list' command."""
    
    @patch('devs.cli.Project')
    def test_list_containers(self, mock_project_class, cli_runner, temp_project):
        """Test listing containers for current project."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.info.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project

        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.list_containers.return_value = [
                MockContainer("/dev-test-org-test-repo-alice", "running", {
                    "devs.project": "test-org-test-repo",
                    "devs.name": "alice"
                }),
                MockContainer("/dev-test-org-test-repo-bob", "exited", {
                    "devs.project": "test-org-test-repo",
                    "devs.name": "bob"
                })
            ]
            mock_container_manager_class.return_value = mock_container_manager

            # Run command
            result = cli_runner.invoke(cli, ['list'])

            # Verify output
            assert result.exit_code == 0
            assert "Active devcontainers for project: test-org-test-repo" in result.output
            assert "alice" in result.output
            assert "running" in result.output
            assert "bob" in result.output
            assert "exited" in result.output
    
    @patch('devs.cli.Project')
    def test_list_no_containers(self, mock_project_class, cli_runner, temp_project):
        """Test listing when no containers exist."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.info.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project

        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # No containers
            mock_container_manager = Mock()
            mock_container_manager.list_containers.return_value = []
            mock_container_manager_class.return_value = mock_container_manager

            # Run command
            result = cli_runner.invoke(cli, ['list'])

            # Verify output
            assert result.exit_code == 0
            assert "No active devcontainers found" in result.output
    
    @patch('devs.cli.Project')
    def test_list_all_containers(self, mock_project_class, cli_runner, temp_project):
        """Test listing all devs containers - --all-projects not yet implemented."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.info.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project

        # Run command with --all-projects (not --all)
        result = cli_runner.invoke(cli, ['list', '--all-projects'])

        # --all-projects is not implemented yet, verify the output message
        assert result.exit_code == 0
        assert "--all-projects not implemented yet" in result.output


class TestStatusCommand:
    """Test suite for 'devs status' command."""

    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ExternalToolIntegration')
    @patch('devs.cli.Project')
    def test_status_all_good(self, mock_project_class, mock_external_tools_class,
                           mock_workspace_manager_class, cli_runner, temp_project):
        """Test status command when everything is configured correctly."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.info.directory = str(temp_project)
        mock_project.info.is_git_repo = True
        mock_project.info.git_remote_url = "https://github.com/test-org/test-repo.git"
        mock_project.check_devcontainer_config.return_value = None  # No exception = config found
        mock_project_class.return_value = mock_project

        mock_external_tools = Mock()
        mock_external_tools.print_dependency_status.return_value = None
        mock_external_tools_class.return_value = mock_external_tools

        mock_workspace_manager = Mock()
        mock_workspace_manager.list_workspaces.return_value = []
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command
        result = cli_runner.invoke(cli, ['status'])

        # Verify output
        assert result.exit_code == 0
        assert "Project: test-org-test-repo" in result.output
        assert "DevContainer config: ✅ Found in project" in result.output

    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ExternalToolIntegration')
    @patch('devs.cli.Project')
    def test_status_missing_dependencies(self, mock_project_class, mock_external_tools_class,
                                       mock_workspace_manager_class, cli_runner, temp_project):
        """Test status command with missing dependencies - just verifies command runs."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.info.directory = str(temp_project)
        mock_project.info.is_git_repo = True
        mock_project.info.git_remote_url = None
        mock_project.check_devcontainer_config.return_value = None
        mock_project_class.return_value = mock_project

        mock_external_tools = Mock()
        mock_external_tools.print_dependency_status.return_value = None
        mock_external_tools_class.return_value = mock_external_tools

        mock_workspace_manager = Mock()
        mock_workspace_manager.list_workspaces.return_value = []
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command
        result = cli_runner.invoke(cli, ['status'])

        # Verify command runs without error
        assert result.exit_code == 0
        assert "Project: test-org-test-repo" in result.output

    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ExternalToolIntegration')
    @patch('devs.cli.Project')
    def test_status_no_devcontainer(self, mock_project_class, mock_external_tools_class,
                                   mock_workspace_manager_class, cli_runner, temp_project):
        """Test status command without devcontainer config - uses default template."""
        from devs.exceptions import DevcontainerConfigError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.info.directory = str(temp_project)
        mock_project.info.is_git_repo = True
        mock_project.info.git_remote_url = None
        mock_project.check_devcontainer_config.side_effect = DevcontainerConfigError("No config")
        mock_project_class.return_value = mock_project

        mock_external_tools = Mock()
        mock_external_tools.print_dependency_status.return_value = None
        mock_external_tools_class.return_value = mock_external_tools

        mock_workspace_manager = Mock()
        mock_workspace_manager.list_workspaces.return_value = []
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Run command
        result = cli_runner.invoke(cli, ['status'])

        # Verify output - now uses default template message
        assert result.exit_code == 0
        assert "Will use default template" in result.output


class TestShellCommand:
    """Test suite for 'devs shell' command."""

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_shell_interactive(self, mock_container_manager_class, mock_workspace_manager_class,
                               mock_get_project, cli_runner, temp_project):
        """Test opening interactive shell in container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager.exec_shell.return_value = None
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['shell', 'alice'])

        # Verify - shell command runs container's exec_shell method
        assert result.exit_code == 0
        mock_container_manager.exec_shell.assert_called_once()

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_shell_with_command(self, mock_container_manager_class, mock_workspace_manager_class,
                               mock_get_project, cli_runner, temp_project):
        """Test shell command - the shell command doesn't take a -c option, it opens interactive shell."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager.exec_shell.return_value = None
        mock_container_manager_class.return_value = mock_container_manager

        # Shell command opens interactive shell - no -c option
        result = cli_runner.invoke(cli, ['shell', 'alice'])

        # Verify
        assert result.exit_code == 0
        mock_container_manager.exec_shell.assert_called_once()

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_shell_container_not_running(self, mock_container_manager_class, mock_workspace_manager_class,
                                        mock_get_project, cli_runner, temp_project):
        """Test shell command when container fails to start."""
        from devs.exceptions import ContainerError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Container manager raises error
        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.side_effect = ContainerError("Container failed")
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['shell', 'alice'])

        # Verify error
        assert result.exit_code == 1
        assert "Error opening shell" in result.output or "Container failed" in result.output


class TestClaudeCommand:
    """Test suite for 'devs claude' command."""

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_claude_command(self, mock_container_manager_class, mock_workspace_manager_class,
                           mock_get_project, cli_runner, temp_project):
        """Test running Claude command in container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager.exec_claude.return_value = (True, "Claude response", None, None)
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt'])

        # Verify
        assert result.exit_code == 0
        assert "Executing Claude in alice" in result.output
        mock_container_manager.exec_claude.assert_called_once()

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_claude_container_not_running(self, mock_container_manager_class, mock_workspace_manager_class,
                                         mock_get_project, cli_runner, temp_project):
        """Test Claude command when container fails to start."""
        from devs.exceptions import ContainerError

        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        # Container manager raises error
        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.side_effect = ContainerError("Container failed")
        mock_container_manager_class.return_value = mock_container_manager

        # Run command
        result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt'])

        # Verify error
        assert result.exit_code == 1
        assert "Error executing Claude" in result.output or "Container failed" in result.output

    @patch('devs.cli.get_project')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.ContainerManager')
    def test_claude_with_env_vars(self, mock_container_manager_class, mock_workspace_manager_class,
                                  mock_get_project, cli_runner, temp_project, monkeypatch):
        """Test Claude command with environment variables passed via --env."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_get_project.return_value = mock_project

        mock_workspace_manager = Mock()
        mock_workspace_manager.create_workspace.return_value = temp_project
        mock_workspace_manager_class.return_value = mock_workspace_manager

        mock_container_manager = Mock()
        mock_container_manager.ensure_container_running.return_value = True
        mock_container_manager.exec_claude.return_value = (True, "Claude response", None, None)
        mock_container_manager_class.return_value = mock_container_manager

        # Run command with env vars
        result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt', '--env', 'TEST_VAR=test_value'])

        # Verify success
        assert result.exit_code == 0
        # Verify env vars message appears
        assert "Environment variables" in result.output