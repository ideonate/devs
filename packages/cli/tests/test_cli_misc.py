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
        mock_project.name = "test-org-test-repo"
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
            assert "Active development environments for test-org-test-repo:" in result.output
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
        mock_project.name = "test-org-test-repo"
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
            assert "No active development environments found" in result.output
    
    @patch('devs.cli.Project')
    def test_list_all_containers(self, mock_project_class, cli_runner, temp_project):
        """Test listing all devs containers across projects."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.list_all_containers.return_value = [
                MockContainer("/dev-test-org-test-repo-alice", "running", {
                    "devs.project": "test-org-test-repo",
                    "devs.name": "alice"
                }),
                MockContainer("/dev-other-org-other-repo-charlie", "running", {
                    "devs.project": "other-org-other-repo",
                    "devs.name": "charlie"
                })
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            # Run command with --all
            result = cli_runner.invoke(cli, ['list', '--all'])
            
            # Verify output
            assert result.exit_code == 0
            assert "All active devs containers:" in result.output
            assert "test-org-test-repo" in result.output
            assert "alice" in result.output
            assert "other-org-other-repo" in result.output
            assert "charlie" in result.output


class TestStatusCommand:
    """Test suite for 'devs status' command."""
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_status_all_good(self, mock_external_tools_class, mock_project_class, 
                           cli_runner, temp_project):
        """Test status command when everything is configured correctly."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools = Mock()
        mock_external_tools.get_dependency_status.return_value = {
            "docker": True,
            "vscode": True,
            "devcontainer_cli": True
        }
        mock_external_tools_class.return_value = mock_external_tools
        
        # Run command
        result = cli_runner.invoke(cli, ['status'])
        
        # Verify output
        assert result.exit_code == 0
        assert "Project Status" in result.output
        assert "Project: test-org-test-repo" in result.output
        assert "DevContainer Config: ✓ Found" in result.output
        assert "Dependencies" in result.output
        assert "Docker: ✓ Available" in result.output
        assert "VS Code: ✓ Available" in result.output
        assert "DevContainer CLI: ✓ Available" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_status_missing_dependencies(self, mock_external_tools_class, mock_project_class,
                                       cli_runner, temp_project):
        """Test status command with missing dependencies."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools = Mock()
        mock_external_tools.get_dependency_status.return_value = {
            "docker": True,
            "vscode": False,
            "devcontainer_cli": False
        }
        mock_external_tools_class.return_value = mock_external_tools
        
        # Run command
        result = cli_runner.invoke(cli, ['status'])
        
        # Verify output
        assert result.exit_code == 0
        assert "Docker: ✓ Available" in result.output
        assert "VS Code: ✗ Not found" in result.output
        assert "DevContainer CLI: ✗ Not found" in result.output
    
    @patch('devs.cli.Project')
    def test_status_no_devcontainer(self, mock_project_class, cli_runner, temp_project):
        """Test status command without devcontainer config."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = False
        mock_project_class.return_value = mock_project
        
        # Run command
        result = cli_runner.invoke(cli, ['status'])
        
        # Verify output
        assert result.exit_code == 0
        assert "DevContainer Config: ✗ Not found" in result.output


class TestShellCommand:
    """Test suite for 'devs shell' command."""
    
    @patch('devs.cli.Project')
    def test_shell_interactive(self, mock_project_class, cli_runner, temp_project):
        """Test opening interactive shell in container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('subprocess.run') as mock_run:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            # Mock subprocess
            mock_run.return_value = Mock(returncode=0)
            
            # Run command
            result = cli_runner.invoke(cli, ['shell', 'alice'])
            
            # Verify
            assert result.exit_code == 0
            mock_run.assert_called_once()
            
            # Check docker exec command
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "docker"
            assert cmd[1] == "exec"
            assert "-it" in cmd
            assert "dev-test-org-test-repo-alice" in cmd
            assert "/bin/bash" in cmd or "/bin/zsh" in cmd
    
    @patch('devs.cli.Project')
    def test_shell_with_command(self, mock_project_class, cli_runner, temp_project):
        """Test running specific command in container shell."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.exec_in_container.return_value = (0, "Hello from container")
            mock_container_manager_class.return_value = mock_container_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['shell', 'alice', '-c', 'echo "Hello"'])
            
            # Verify
            assert result.exit_code == 0
            assert "Hello from container" in result.output
            
            # Verify exec call
            mock_container_manager.exec_in_container.assert_called_once_with(
                "alice",
                'echo "Hello"'
            )
    
    @patch('devs.cli.Project')
    def test_shell_container_not_running(self, mock_project_class, cli_runner, temp_project):
        """Test shell command when container is not running."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # Container not running
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = False
            mock_container_manager_class.return_value = mock_container_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['shell', 'alice'])
            
            # Verify error
            assert result.exit_code == 1
            assert "Container 'alice' is not running" in result.output
            assert "Use 'devs start alice' first" in result.output


class TestClaudeCommand:
    """Test suite for 'devs claude' command."""
    
    @patch('devs.cli.Project')
    def test_claude_command(self, mock_project_class, cli_runner, temp_project):
        """Test running Claude command in container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.ClaudeIntegration') as mock_claude_class:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            # Setup Claude integration mock
            mock_claude = Mock()
            mock_claude.run_claude_command.return_value = (0, "Claude response")
            mock_claude_class.return_value = mock_claude
            
            # Run command
            result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt'])
            
            # Verify
            assert result.exit_code == 0
            assert "Claude response" in result.output
            
            # Verify Claude was called correctly
            mock_claude.run_claude_command.assert_called_once_with(
                "alice",
                "test prompt"
            )
    
    @patch('devs.cli.Project')
    def test_claude_container_not_running(self, mock_project_class, cli_runner, temp_project):
        """Test Claude command when container is not running."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class:
            # Container not running
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = False
            mock_container_manager_class.return_value = mock_container_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt'])
            
            # Verify error
            assert result.exit_code == 1
            assert "Container 'alice' is not running" in result.output
    
    @patch('devs.cli.Project')
    def test_claude_with_env_vars(self, mock_project_class, cli_runner, temp_project, monkeypatch):
        """Test Claude command with environment variables."""
        # Set environment variable
        monkeypatch.setenv("CLAUDE_API_KEY", "test-key-123")
        
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.ClaudeIntegration') as mock_claude_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_claude = Mock()
            mock_claude.run_claude_command.return_value = (0, "Claude response")
            mock_claude_class.return_value = mock_claude
            
            # Run command
            result = cli_runner.invoke(cli, ['claude', 'alice', 'test prompt'])
            
            # Verify success
            assert result.exit_code == 0
            
            # Claude integration should have access to container manager
            mock_claude_class.assert_called_once_with(mock_project, mock_container_manager)