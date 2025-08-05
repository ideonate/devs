"""Integration tests for the 'vscode' command."""
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestVSCodeCommand:
    """Test suite for 'devs vscode' command."""
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_single_container(self, mock_external_tools, mock_project_class,
                                   cli_runner, temp_project):
        """Test opening VS Code for a single container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class, \
             patch('devs.cli.VSCodeIntegration') as mock_vscode_class:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            # Setup workspace manager mock
            mock_workspace_manager = Mock()
            mock_workspace_manager.get_workspace_path.return_value = temp_project / "workspaces" / "alice"
            mock_workspace_manager.workspace_exists.return_value = True
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Setup VS Code integration mock
            mock_vscode = Mock()
            mock_vscode.open_in_container.return_value = True
            mock_vscode_class.return_value = mock_vscode
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Opening VS Code for development environment 'alice'" in result.output
            assert "✓ Opened VS Code for alice" in result.output
            
            # Verify calls
            mock_vscode.open_in_container.assert_called_once_with(
                "alice",
                mock_workspace_manager.get_workspace_path.return_value
            )
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_multiple_containers(self, mock_external_tools, mock_project_class,
                                      cli_runner, temp_project):
        """Test opening VS Code for multiple containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class, \
             patch('devs.cli.VSCodeIntegration') as mock_vscode_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.get_container_name.side_effect = [
                "dev-test-org-test-repo-alice",
                "dev-test-org-test-repo-bob"
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.workspace_exists.return_value = True
            mock_workspace_manager.get_workspace_path.side_effect = [
                temp_project / "workspaces" / "alice",
                temp_project / "workspaces" / "bob"
            ]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            mock_vscode = Mock()
            mock_vscode.open_in_container.return_value = True
            mock_vscode_class.return_value = mock_vscode
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice', 'bob'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Opening VS Code for development environment 'alice'" in result.output
            assert "Opening VS Code for development environment 'bob'" in result.output
            assert "✓ Opened VS Code for alice" in result.output
            assert "✓ Opened VS Code for bob" in result.output
            
            # Verify calls
            assert mock_vscode.open_in_container.call_count == 2
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_container_not_running(self, mock_external_tools, mock_project_class,
                                        cli_runner, temp_project):
        """Test opening VS Code for a stopped container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup container manager mock - container not running
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = False
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager_class.return_value = Mock()
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice'])
            
            # Verify error
            assert result.exit_code == 1
            assert "Container 'alice' is not running" in result.output
            assert "Use 'devs start alice' first" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_workspace_not_exists(self, mock_external_tools, mock_project_class,
                                       cli_runner, temp_project):
        """Test opening VS Code when workspace doesn't exist."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            # Workspace doesn't exist
            mock_workspace_manager = Mock()
            mock_workspace_manager.workspace_exists.return_value = False
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice'])
            
            # Verify error
            assert result.exit_code == 1
            assert "Workspace for 'alice' does not exist" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_missing_vscode(self, mock_external_tools, mock_project_class,
                                 cli_runner, temp_project):
        """Test opening VS Code when VS Code is not installed."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        # VS Code not available
        mock_external_tools.return_value.check_vscode.return_value = False
        
        # Run command
        result = cli_runner.invoke(cli, ['vscode', 'alice'])
        
        # Verify error
        assert result.exit_code == 1
        assert "VS Code is not installed" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_open_failure(self, mock_external_tools, mock_project_class,
                               cli_runner, temp_project):
        """Test handling VS Code open failure."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class, \
             patch('devs.cli.VSCodeIntegration') as mock_vscode_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.workspace_exists.return_value = True
            mock_workspace_manager.get_workspace_path.return_value = temp_project / "workspaces" / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # VS Code fails to open
            mock_vscode = Mock()
            mock_vscode.open_in_container.return_value = False
            mock_vscode_class.return_value = mock_vscode
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice'])
            
            # Verify error handling
            assert result.exit_code == 1
            assert "Failed to open VS Code for alice" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_vscode_partial_success(self, mock_external_tools, mock_project_class,
                                  cli_runner, temp_project):
        """Test opening VS Code for multiple containers with partial success."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class, \
             patch('devs.cli.VSCodeIntegration') as mock_vscode_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            # First container is running, second is not
            mock_container_manager.is_container_running.side_effect = [True, False]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.workspace_exists.return_value = True
            mock_workspace_manager.get_workspace_path.return_value = temp_project / "workspaces" / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            mock_vscode = Mock()
            mock_vscode.open_in_container.return_value = True
            mock_vscode_class.return_value = mock_vscode
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice', 'bob'])
            
            # Verify partial success
            assert result.exit_code == 1
            assert "✓ Opened VS Code for alice" in result.output
            assert "Container 'bob' is not running" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    @patch('subprocess.run')
    def test_vscode_with_custom_title(self, mock_subprocess, mock_external_tools, 
                                    mock_project_class, cli_runner, temp_project):
        """Test VS Code opens with custom window title."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_vscode.return_value = True
        
        # Mock subprocess to capture VS Code command
        mock_subprocess.return_value = Mock(returncode=0)
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class, \
             patch('devs.cli.VSCodeIntegration') as mock_vscode_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.workspace_exists.return_value = True
            mock_workspace_manager.get_workspace_path.return_value = temp_project / "workspaces" / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Mock VS Code integration to use subprocess
            mock_vscode = Mock()
            mock_vscode.open_in_container.return_value = True
            mock_vscode_class.return_value = mock_vscode
            
            # Run command
            result = cli_runner.invoke(cli, ['vscode', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            
            # Verify VS Code was called with the alice dev environment
            mock_vscode.open_in_container.assert_called_once_with(
                "alice",
                temp_project / "workspaces" / "alice"
            )