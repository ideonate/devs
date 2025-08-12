"""Tests for live mode functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from devs.cli import cli
from devs.exceptions import ContainerError


class TestLiveMode:
    """Test suite for live mode functionality."""
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_with_live_flag(self, mock_workspace_mgr, mock_container_mgr, mock_get_project, mock_check_deps):
        """Test that start command with --live flag uses current directory."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-project"
        mock_get_project.return_value = mock_project
        
        mock_container = Mock()
        mock_container.ensure_container_running.return_value = True
        mock_container_mgr.return_value = mock_container
        
        mock_workspace = Mock()
        mock_workspace_mgr.return_value = mock_workspace
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, ['start', 'test-dev', '--live'])
        
        # Verify live mode was passed to ensure_container_running
        mock_container.ensure_container_running.assert_called_once()
        call_args = mock_container.ensure_container_running.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify workspace was not created
        mock_workspace.create_workspace.assert_not_called()
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_start_without_live_flag(self, mock_workspace_mgr, mock_container_mgr, mock_get_project, mock_check_deps):
        """Test that start command without --live flag creates workspace."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-project"
        mock_get_project.return_value = mock_project
        
        mock_container = Mock()
        mock_container.ensure_container_running.return_value = True
        mock_container_mgr.return_value = mock_container
        
        mock_workspace = Mock()
        mock_workspace.create_workspace.return_value = Path("/test/workspace")
        mock_workspace_mgr.return_value = mock_workspace
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, ['start', 'test-dev'])
        
        # Verify live mode was not passed
        mock_container.ensure_container_running.assert_called_once()
        call_args = mock_container.ensure_container_running.call_args
        assert call_args.kwargs.get('live') is False
        
        # Verify workspace was created
        mock_workspace.create_workspace.assert_called_once_with('test-dev')
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_vscode_with_live_flag(self, mock_workspace_mgr, mock_container_mgr, mock_get_project, mock_check_deps):
        """Test that vscode command with --live flag uses current directory."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-project"
        mock_get_project.return_value = mock_project
        
        mock_container = Mock()
        mock_container.ensure_container_running.return_value = True
        mock_container_mgr.return_value = mock_container
        
        mock_workspace = Mock()
        mock_workspace_mgr.return_value = mock_workspace
        
        # Mock VSCodeIntegration
        with patch('devs.cli.VSCodeIntegration') as mock_vscode:
            mock_vscode_instance = Mock()
            mock_vscode_instance.launch_multiple_devcontainers.return_value = 1
            mock_vscode.return_value = mock_vscode_instance
            
            # Run command
            runner = CliRunner()
            result = runner.invoke(cli, ['vscode', 'test-dev', '--live'])
            
            # Verify live mode was passed
            mock_container.ensure_container_running.assert_called_once()
            call_args = mock_container.ensure_container_running.call_args
            assert call_args.kwargs.get('live') is True
            
            # Verify workspace was not created
            mock_workspace.create_workspace.assert_not_called()
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_shell_with_live_flag(self, mock_workspace_mgr, mock_container_mgr, mock_get_project, mock_check_deps):
        """Test that shell command with --live flag uses current directory."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-project"
        mock_get_project.return_value = mock_project
        
        mock_container = Mock()
        mock_container.ensure_container_running.return_value = True
        mock_container.exec_shell = Mock()
        mock_container_mgr.return_value = mock_container
        
        mock_workspace = Mock()
        mock_workspace_mgr.return_value = mock_workspace
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, ['shell', 'test-dev', '--live'])
        
        # Verify live mode was passed
        mock_container.ensure_container_running.assert_called_once()
        call_args = mock_container.ensure_container_running.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify exec_shell was called with live=True
        mock_container.exec_shell.assert_called_once()
        call_args = mock_container.exec_shell.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify workspace was not created
        mock_workspace.create_workspace.assert_not_called()
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    def test_claude_with_live_flag(self, mock_workspace_mgr, mock_container_mgr, mock_get_project, mock_check_deps):
        """Test that claude command with --live flag uses current directory."""
        # Setup mocks
        mock_project = Mock()
        mock_project.info.name = "test-project"
        mock_get_project.return_value = mock_project
        
        mock_container = Mock()
        mock_container.ensure_container_running.return_value = True
        mock_container.exec_claude = Mock(return_value=(True, "output", ""))
        mock_container_mgr.return_value = mock_container
        
        mock_workspace = Mock()
        mock_workspace_mgr.return_value = mock_workspace
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, ['claude', 'test-dev', 'test prompt', '--live'])
        
        # Verify live mode was passed
        mock_container.ensure_container_running.assert_called_once()
        call_args = mock_container.ensure_container_running.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify exec_claude was called with live=True
        mock_container.exec_claude.assert_called_once()
        call_args = mock_container.exec_claude.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify workspace was not created
        mock_workspace.create_workspace.assert_not_called()


class TestContainerLiveLabels:
    """Test container labeling for live mode."""
    
    @patch('devs_common.core.container.DockerClient')
    @patch('devs_common.core.container.DevContainerCLI')
    def test_container_labels_with_live_mode(self, mock_devcontainer_cls, mock_docker_cls):
        """Test that containers get proper labels in live mode."""
        from devs_common.core.container import ContainerManager
        from devs_common.core.project import Project
        
        # Setup Docker mock
        mock_docker = Mock()
        # First call returns no existing containers, second call returns the created one
        mock_docker.find_containers_by_labels.side_effect = [
            [],  # No existing containers
            [{   # After devcontainer.up, return the created container
                'name': 'dev-test-project-test',
                'status': 'running',
                'labels': {
                    'devs.project': 'test-project',
                    'devs.dev': 'test',
                    'devs.live': 'true'
                }
            }]
        ]
        mock_docker.find_images_by_pattern.return_value = []  # No existing images
        mock_docker.exec_command.return_value = True  # Health check passes
        mock_docker_cls.return_value = mock_docker
        
        # Setup DevContainer mock
        mock_devcontainer = Mock()
        mock_devcontainer.up.return_value = True
        mock_devcontainer_cls.return_value = mock_devcontainer
        
        # Create mocks
        mock_project = Mock(spec=Project)
        mock_project.info.name = "test-project"
        mock_project.project_dir = Path("/test/project")
        mock_project.get_container_name.return_value = "dev-test-project-test"
        mock_project.get_workspace_name.return_value = "test-project-test"
        
        # Create ContainerManager
        container_mgr = ContainerManager(mock_project)
        
        # Call ensure_container_running with live=True
        with patch.object(container_mgr, 'should_rebuild_image', return_value=(False, "")):
            container_mgr.ensure_container_running("test", Path("/test"), live=True)
        
        # Check that devcontainer.up was called with live=True
        mock_devcontainer.up.assert_called_once()
        call_args = mock_devcontainer.up.call_args
        assert call_args.kwargs.get('live') is True
    
    @patch('devs_common.core.container.DockerClient')
    @patch('devs_common.core.container.DevContainerCLI')
    def test_container_mode_mismatch_error(self, mock_devcontainer_cls, mock_docker_cls):
        """Test that error is raised when container mode doesn't match request."""
        from devs_common.core.container import ContainerManager
        from devs_common.core.project import Project
        
        # Setup Docker mock
        mock_docker = Mock()
        # Simulate existing container in copy mode
        mock_docker.find_containers_by_labels.return_value = [{
            'name': 'test-container',
            'status': 'running',
            'labels': {
                'devs.project': 'test-project',
                'devs.dev': 'test',
                # No 'devs.live' label means copy mode
            }
        }]
        mock_docker.find_images_by_pattern.return_value = []  # No existing images
        mock_docker_cls.return_value = mock_docker
        
        # Setup DevContainer mock
        mock_devcontainer = Mock()
        mock_devcontainer_cls.return_value = mock_devcontainer
        
        # Create mocks
        mock_project = Mock(spec=Project)
        mock_project.info.name = "test-project"
        mock_project.project_dir = Path("/test/project")
        
        # Create ContainerManager
        container_mgr = ContainerManager(mock_project)
        
        # Try to ensure container with live=True when existing is copy mode
        with pytest.raises(ContainerError) as exc_info:
            container_mgr.ensure_container_running("test", Path("/test"), live=True)
        
        assert "already exists in workspace copy mode" in str(exc_info.value)
        assert "but live mode was requested" in str(exc_info.value)