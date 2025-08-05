"""Integration tests for the 'start' command."""
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from tests.conftest import MockContainer


class TestStartCommand:
    """Test suite for 'devs start' command."""
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_single_container(self, mock_external_tools, mock_project_class, 
                                  cli_runner, temp_project, mock_docker_client):
        """Test starting a single container."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup container manager mock
            mock_container_manager = Mock()
            mock_container_manager.ensure_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            # Setup workspace manager mock
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.return_value = temp_project / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Starting development environment 'alice'" in result.output
            assert "✓ Created workspace for alice" in result.output
            assert "✓ Started container dev-test-org-test-repo-alice" in result.output
            assert "Successfully started: alice" in result.output
            
            # Verify calls
            mock_workspace_manager.create_workspace.assert_called_once_with("alice")
            mock_container_manager.ensure_container_running.assert_called_once()
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_multiple_containers(self, mock_external_tools, mock_project_class,
                                     cli_runner, temp_project):
        """Test starting multiple containers."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.ensure_container_running.return_value = True
            mock_container_manager.get_container_name.side_effect = [
                "dev-test-org-test-repo-alice",
                "dev-test-org-test-repo-bob"
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.side_effect = [
                temp_project / "alice",
                temp_project / "bob"
            ]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice', 'bob'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Starting development environment 'alice'" in result.output
            assert "Starting development environment 'bob'" in result.output
            assert "Successfully started: alice, bob" in result.output
            
            # Verify calls
            assert mock_workspace_manager.create_workspace.call_count == 2
            assert mock_container_manager.ensure_container_running.call_count == 2
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_container_already_running(self, mock_external_tools, mock_project_class,
                                           cli_runner, temp_project):
        """Test starting a container that's already running."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.is_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            assert "Container 'alice' is already running" in result.output
    
    @patch('devs.cli.Project')
    def test_start_no_devcontainer_config(self, mock_project_class, cli_runner, temp_project):
        """Test starting container without devcontainer configuration."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.has_devcontainer_config.return_value = False
        mock_project_class.return_value = mock_project
        
        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])
        
        # Verify error
        assert result.exit_code == 1
        assert "No .devcontainer/devcontainer.json found" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_workspace_creation_failure(self, mock_external_tools, mock_project_class,
                                            cli_runner, temp_project):
        """Test handling workspace creation failure."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup workspace manager to fail
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.side_effect = Exception("Permission denied")
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            mock_container_manager_class.return_value = Mock()
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice'])
            
            # Verify error handling
            assert result.exit_code == 1
            assert "Failed to create workspace" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_container_creation_failure(self, mock_external_tools, mock_project_class,
                                            cli_runner, temp_project):
        """Test handling container creation failure."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.return_value = temp_project / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            mock_container_manager = Mock()
            mock_container_manager.ensure_container_running.return_value = False
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice'])
            
            # Verify error handling
            assert result.exit_code == 1
            assert "Failed to start container" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_missing_dependencies(self, mock_external_tools, mock_project_class,
                                      cli_runner, temp_project):
        """Test starting container with missing dependencies."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project_class.return_value = mock_project
        
        # Mock missing Docker
        mock_external_tools.return_value.check_all.return_value = False
        mock_external_tools.return_value.check_docker.return_value = False
        
        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])
        
        # Verify error
        assert result.exit_code == 1
        assert "Missing required dependencies" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_with_environment_variables(self, mock_external_tools, mock_project_class,
                                            cli_runner, temp_project, monkeypatch):
        """Test starting container with environment variables."""
        # Set environment variables
        monkeypatch.setenv("GH_TOKEN", "test-token-123")
        monkeypatch.setenv("CUSTOM_VAR", "custom-value")
        
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            mock_container_manager.ensure_container_running.return_value = True
            mock_container_manager.get_container_name.return_value = "dev-test-org-test-repo-alice"
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.return_value = temp_project / "alice"
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice'])
            
            # Verify success
            assert result.exit_code == 0
            
            # Verify environment variables were passed
            call_args = mock_container_manager.ensure_container_running.call_args
            assert call_args is not None
    
    @patch('devs.cli.Project')
    def test_start_invalid_project_directory(self, mock_project_class, cli_runner):
        """Test starting container from invalid project directory."""
        # Setup mock to raise exception
        mock_project_class.side_effect = Exception("Not a valid project directory")
        
        # Run command
        result = cli_runner.invoke(cli, ['start', 'alice'])
        
        # Verify error
        assert result.exit_code == 1
        assert "Error" in result.output
    
    @patch('devs.cli.Project')
    @patch('devs.cli.ExternalToolIntegration')
    def test_start_partial_success(self, mock_external_tools, mock_project_class,
                                 cli_runner, temp_project):
        """Test starting multiple containers with partial success."""
        # Setup mocks
        mock_project = Mock()
        mock_project.path = temp_project
        mock_project.name = "test-org-test-repo"
        mock_project.has_devcontainer_config.return_value = True
        mock_project_class.return_value = mock_project
        
        mock_external_tools.return_value.check_all.return_value = True
        
        with patch('devs.cli.ContainerManager') as mock_container_manager_class, \
             patch('devs.cli.WorkspaceManager') as mock_workspace_manager_class:
            
            # Setup mocks
            mock_container_manager = Mock()
            # First container succeeds, second fails
            mock_container_manager.ensure_container_running.side_effect = [True, False]
            mock_container_manager.get_container_name.side_effect = [
                "dev-test-org-test-repo-alice",
                "dev-test-org-test-repo-bob"
            ]
            mock_container_manager_class.return_value = mock_container_manager
            
            mock_workspace_manager = Mock()
            mock_workspace_manager.create_workspace.side_effect = [
                temp_project / "alice",
                temp_project / "bob"
            ]
            mock_workspace_manager_class.return_value = mock_workspace_manager
            
            # Run command
            result = cli_runner.invoke(cli, ['start', 'alice', 'bob'])
            
            # Verify partial success
            assert result.exit_code == 1
            assert "Successfully started: alice" in result.output
            assert "Failed to start: bob" in result.output