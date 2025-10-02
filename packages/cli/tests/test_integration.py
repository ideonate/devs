"""Tests for VSCodeIntegration and ExternalToolIntegration classes."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from devs.core.integration import VSCodeIntegration, ExternalToolIntegration
from devs_common.exceptions import VSCodeError, DependencyError


class TestVSCodeIntegration:
    """Test suite for VSCodeIntegration class."""
    
    def test_init(self, mock_project):
        """Test VSCodeIntegration initialization."""
        integration = VSCodeIntegration(mock_project)
        assert integration.project == mock_project
    
    @patch('subprocess.run')
    def test_open_in_container_success(self, mock_run, mock_vscode_integration, tmp_path):
        """Test successful VS Code opening in container."""
        mock_run.return_value = Mock(returncode=0)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        
        # Patch _run_command to use our mock
        mock_vscode_integration._run_command = lambda cmd, **kwargs: mock_run(cmd, **kwargs).returncode == 0
        
        result = mock_vscode_integration.open_in_container("alice", workspace_path)
        
        assert result is True
    
    @patch('subprocess.run')
    def test_open_in_container_with_uri(self, mock_run, mock_vscode_integration, tmp_path):
        """Test VS Code opens with correct devcontainer URI."""
        mock_run.return_value = Mock(returncode=0)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        
        # Override _run_command to capture the command
        captured_cmd = []
        def capture_command(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return True
        
        mock_vscode_integration._run_command = capture_command
        
        result = mock_vscode_integration.open_in_container("alice", workspace_path)
        
        assert result is True
        # Verify the command structure
        assert "code" in captured_cmd
        assert "--folder-uri" in captured_cmd
        
        # Find the URI argument
        uri_index = captured_cmd.index("--folder-uri") + 1
        uri = captured_cmd[uri_index]
        
        # Verify URI format
        assert uri.startswith("vscode-remote://dev-container+")
        assert "/workspaces/" in uri
        assert "test-org-test-repo-alice" in uri
    
    @patch('subprocess.run')
    def test_open_in_container_failure(self, mock_run, mock_vscode_integration, tmp_path):
        """Test handling VS Code open failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Command not found")
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        
        mock_vscode_integration._run_command = lambda cmd, **kwargs: mock_run(cmd, **kwargs).returncode == 0
        
        result = mock_vscode_integration.open_in_container("alice", workspace_path)
        
        assert result is False
    
    def test_generate_devcontainer_uri(self, mock_vscode_integration, tmp_path):
        """Test devcontainer URI generation."""
        workspace_path = tmp_path / "workspace"
        
        uri = mock_vscode_integration._generate_devcontainer_uri("alice", workspace_path)
        
        # Verify URI components
        assert uri.startswith("vscode-remote://dev-container+")
        assert "/workspaces/" in uri
        assert "test-org-test-repo-alice" in uri
        
        # Verify hex encoding
        import binascii
        hex_part = uri.split("+")[1].split("/")[0]
        # Should be valid hex
        binascii.unhexlify(hex_part)
    
    @patch('subprocess.run')
    def test_run_command_success(self, mock_run, mock_vscode_integration):
        """Test successful command execution."""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        result = mock_vscode_integration._run_command(["echo", "test"])
        
        assert result is True
        mock_run.assert_called_once_with(
            ["echo", "test"],
            capture_output=True,
            text=True,
            check=False
        )
    
    @patch('subprocess.run')
    def test_run_command_failure(self, mock_run, mock_vscode_integration):
        """Test failed command execution."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error")
        
        result = mock_vscode_integration._run_command(["false"])
        
        assert result is False
    
    @patch('subprocess.run')
    def test_run_command_exception(self, mock_run, mock_vscode_integration):
        """Test command execution with exception."""
        mock_run.side_effect = FileNotFoundError("Command not found")
        
        result = mock_vscode_integration._run_command(["nonexistent"])
        
        assert result is False


class TestExternalToolIntegration:
    """Test suite for ExternalToolIntegration class."""
    
    def test_init(self):
        """Test ExternalToolIntegration initialization."""
        integration = ExternalToolIntegration()
        assert integration is not None
    
    @patch('shutil.which')
    def test_check_docker_available(self, mock_which):
        """Test Docker availability check when Docker is available."""
        mock_which.return_value = "/usr/bin/docker"
        integration = ExternalToolIntegration()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            result = integration.check_docker()
            
            assert result is True
            mock_which.assert_called_once_with("docker")
            mock_run.assert_called_once()
    
    @patch('shutil.which')
    def test_check_docker_not_installed(self, mock_which):
        """Test Docker availability check when Docker is not installed."""
        mock_which.return_value = None
        integration = ExternalToolIntegration()
        
        result = integration.check_docker()
        
        assert result is False
    
    @patch('shutil.which')
    def test_check_docker_not_running(self, mock_which):
        """Test Docker availability check when Docker daemon is not running."""
        mock_which.return_value = "/usr/bin/docker"
        integration = ExternalToolIntegration()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="Cannot connect to Docker daemon")
            
            result = integration.check_docker()
            
            assert result is False
    
    @patch('shutil.which')
    def test_check_vscode_available(self, mock_which):
        """Test VS Code availability check when VS Code is available."""
        mock_which.return_value = "/usr/bin/code"
        integration = ExternalToolIntegration()
        
        result = integration.check_vscode()
        
        assert result is True
        mock_which.assert_called_once_with("code")
    
    @patch('shutil.which')
    def test_check_vscode_not_available(self, mock_which):
        """Test VS Code availability check when VS Code is not available."""
        mock_which.return_value = None
        integration = ExternalToolIntegration()
        
        result = integration.check_vscode()
        
        assert result is False
    
    @patch('subprocess.run')
    def test_check_devcontainer_cli_available(self, mock_run):
        """Test devcontainer CLI availability check when available."""
        mock_run.return_value = Mock(returncode=0, stdout="0.50.0")
        integration = ExternalToolIntegration()
        
        result = integration.check_devcontainer_cli()
        
        assert result is True
        mock_run.assert_called_once()
        # Verify command includes version check
        cmd = mock_run.call_args[0][0]
        assert "devcontainer" in cmd
        assert "--version" in cmd
    
    @patch('subprocess.run')
    def test_check_devcontainer_cli_not_available(self, mock_run):
        """Test devcontainer CLI availability check when not available."""
        mock_run.side_effect = FileNotFoundError()
        integration = ExternalToolIntegration()
        
        result = integration.check_devcontainer_cli()
        
        assert result is False
    
    def test_check_all_success(self):
        """Test checking all dependencies when all are available."""
        integration = ExternalToolIntegration()
        
        # Mock all checks to return True
        integration.check_docker = Mock(return_value=True)
        integration.check_vscode = Mock(return_value=True)
        integration.check_devcontainer_cli = Mock(return_value=True)
        
        result = integration.check_all()
        
        assert result is True
        integration.check_docker.assert_called_once()
        integration.check_vscode.assert_called_once()
        integration.check_devcontainer_cli.assert_called_once()
    
    def test_check_all_missing_docker(self):
        """Test checking all dependencies when Docker is missing."""
        integration = ExternalToolIntegration()
        
        # Mock Docker check to return False
        integration.check_docker = Mock(return_value=False)
        integration.check_vscode = Mock(return_value=True)
        integration.check_devcontainer_cli = Mock(return_value=True)
        
        result = integration.check_all()
        
        assert result is False
    
    def test_get_missing_dependencies(self):
        """Test getting list of missing dependencies."""
        integration = ExternalToolIntegration()
        
        # Mock some dependencies as missing
        integration.check_docker = Mock(return_value=True)
        integration.check_vscode = Mock(return_value=False)
        integration.check_devcontainer_cli = Mock(return_value=False)
        
        missing = integration.get_missing_dependencies()
        
        assert len(missing) == 2
        assert "VS Code" in missing
        assert "DevContainer CLI" in missing
        assert "Docker" not in missing
    
    def test_get_dependency_status(self):
        """Test getting dependency status dictionary."""
        integration = ExternalToolIntegration()
        
        # Mock dependency checks
        integration.check_docker = Mock(return_value=True)
        integration.check_vscode = Mock(return_value=False)
        integration.check_devcontainer_cli = Mock(return_value=True)
        
        status = integration.get_dependency_status()
        
        assert status["docker"] is True
        assert status["vscode"] is False
        assert status["devcontainer_cli"] is True


# Commenting out ClaudeIntegration tests as the class no longer exists
"""
class TestClaudeIntegration:
    '''Test suite for ClaudeIntegration class.'''

    def test_init(self, mock_project, mock_container_manager):
        '''Test ClaudeIntegration initialization.'''
        integration = ClaudeIntegration(mock_project, mock_container_manager)
        assert integration.project == mock_project
        assert integration.container_manager == mock_container_manager

    def test_run_claude_command_success(self, mock_project, mock_container_manager):
        '''Test successful Claude command execution.'''
        integration = ClaudeIntegration(mock_project, mock_container_manager)
        
        # Mock successful execution
        mock_container_manager.exec_in_container.return_value = (0, "Claude output")
        
        exit_code, output = integration.run_claude_command("alice", "test prompt")
        
        assert exit_code == 0
        assert output == "Claude output"
        
        # Verify the command was constructed correctly
        mock_container_manager.exec_in_container.assert_called_once()
        call_args = mock_container_manager.exec_in_container.call_args
        assert call_args[0][0] == "alice"
        assert "claude" in call_args[0][1]
        assert "test prompt" in call_args[0][1]
    
    def test_run_claude_command_with_env(self, mock_project, mock_container_manager, monkeypatch):
        '''Test Claude command execution with environment variables.'''
        monkeypatch.setenv("CLAUDE_API_KEY", "test-key")
        
        integration = ClaudeIntegration(mock_project, mock_container_manager)
        
        # Mock successful execution
        mock_container_manager.exec_in_container.return_value = (0, "Claude output")
        
        exit_code, output = integration.run_claude_command("alice", "test prompt")
        
        assert exit_code == 0
        
        # Verify environment variables were passed
        call_args = mock_container_manager.exec_in_container.call_args
        env_vars = call_args[1].get("env_vars", {})
        assert env_vars.get("CLAUDE_API_KEY") == "test-key"
    
    def test_run_claude_command_failure(self, mock_project, mock_container_manager):
        '''Test Claude command execution failure.'''
        integration = ClaudeIntegration(mock_project, mock_container_manager)
        
        # Mock failed execution
        mock_container_manager.exec_in_container.return_value = (1, "Error: Claude not found")
        
        exit_code, output = integration.run_claude_command("alice", "test prompt")
        
        assert exit_code == 1
        assert "Error: Claude not found" in output
    
    def test_run_claude_command_container_error(self, mock_project, mock_container_manager):
        '''Test Claude command when container execution fails.'''
        integration = ClaudeIntegration(mock_project, mock_container_manager)
        
        # Mock container execution error
        from devs_common.exceptions import ContainerError
        mock_container_manager.exec_in_container.side_effect = ContainerError("Container not running")
        
        with pytest.raises(ContainerError):
            integration.run_claude_command("alice", "test prompt")
"""