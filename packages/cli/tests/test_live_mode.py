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
        mock_workspace.create_workspace.return_value = Path.cwd()
        mock_workspace_mgr.return_value = mock_workspace
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, ['start', 'test-dev', '--live'])
        
        # Verify live mode was passed to ensure_container_running
        mock_container.ensure_container_running.assert_called_once()
        call_args = mock_container.ensure_container_running.call_args
        assert call_args.kwargs.get('live') is True
        
        # Verify workspace.create_workspace was called with live=True
        mock_workspace.create_workspace.assert_called_once_with('test-dev', live=True)
    
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
        
        # Verify workspace was created without live flag
        mock_workspace.create_workspace.assert_called_once_with('test-dev', live=False)
    
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
        mock_workspace.create_workspace.return_value = Path.cwd()
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
            
            # Verify workspace.create_workspace was called with live=True
            mock_workspace.create_workspace.assert_called_once_with('test-dev', live=True)
    
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
        mock_workspace.create_workspace.return_value = Path.cwd()
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
        
        # Verify workspace.create_workspace was called with live=True
        mock_workspace.create_workspace.assert_called_once_with('test-dev', live=True)
    
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
        mock_workspace.create_workspace.return_value = Path.cwd()
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
        
        # Verify workspace.create_workspace was called with live=True and reset_contents=False
        mock_workspace.create_workspace.assert_called_once_with('test-dev', reset_contents=False, live=True)


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


class TestLiveModeDevcontainerTemplate:
    """Test devcontainer template copying in live mode."""
    
    @patch('devs_common.core.workspace.get_template_dir')
    @patch('devs_common.core.workspace.is_devcontainer_gitignored')
    @patch('devs_common.core.workspace.shutil.copytree')
    def test_live_mode_copies_devcontainer_template_when_gitignored(self, mock_copytree, mock_is_gitignored, mock_get_template):
        """Test that devcontainer template is copied in live mode when .devcontainer is gitignored."""
        from devs_common.core.workspace import WorkspaceManager
        from devs_common.core.project import Project
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            
            # Setup project mock
            mock_project = Mock(spec=Project)
            mock_project.project_dir = project_dir
            mock_project.info.name = "test-project"
            mock_project.info.is_git_repo = True
            
            # .devcontainer doesn't exist yet
            devcontainer_path = project_dir / ".devcontainer"
            assert not devcontainer_path.exists()
            
            # Mock that .devcontainer is in gitignore
            mock_is_gitignored.return_value = True
            
            # Mock template directory
            template_dir = Path("/mock/template/dir")
            mock_get_template.return_value = template_dir
            
            # Create workspace manager
            workspace_mgr = WorkspaceManager(mock_project)
            
            # Call create_workspace with live=True
            result = workspace_mgr.create_workspace("test", live=True)
            
            # Should return the project directory (live mode)
            assert result == project_dir
            
            # Should have checked if .devcontainer is gitignored
            mock_is_gitignored.assert_called_once_with(project_dir)
            
            # Should have copied the template
            mock_copytree.assert_called_once_with(template_dir, devcontainer_path, dirs_exist_ok=True)
    
    @patch('devs_common.core.workspace.get_template_dir')
    @patch('devs_common.core.workspace.is_devcontainer_gitignored')
    @patch('devs_common.core.workspace.shutil.copytree')
    def test_live_mode_no_copy_when_devcontainer_exists(self, mock_copytree, mock_is_gitignored, mock_get_template):
        """Test that devcontainer template is NOT copied in live mode when .devcontainer already exists."""
        from devs_common.core.workspace import WorkspaceManager
        from devs_common.core.project import Project
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            
            # Create existing .devcontainer
            devcontainer_path = project_dir / ".devcontainer"
            devcontainer_path.mkdir(parents=True)
            (devcontainer_path / "devcontainer.json").write_text("{}")
            
            # Setup project mock
            mock_project = Mock(spec=Project)
            mock_project.project_dir = project_dir
            mock_project.info.name = "test-project"
            mock_project.info.is_git_repo = True
            
            # Create workspace manager
            workspace_mgr = WorkspaceManager(mock_project)
            
            # Call create_workspace with live=True
            result = workspace_mgr.create_workspace("test", live=True)
            
            # Should return the project directory (live mode)
            assert result == project_dir

            # When .devcontainer exists, the implementation checks if it's gitignored
            # to warn about outdated templates, but should NOT copy template
            mock_copytree.assert_not_called()
    
    @patch('devs_common.core.workspace.get_template_dir')
    @patch('devs_common.core.workspace.is_devcontainer_gitignored')
    @patch('devs_common.core.workspace.shutil.copytree')
    def test_live_mode_no_copy_when_not_gitignored(self, mock_copytree, mock_is_gitignored, mock_get_template):
        """Test that devcontainer template is NOT copied in live mode when .devcontainer is not gitignored."""
        from devs_common.core.workspace import WorkspaceManager
        from devs_common.core.project import Project
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            
            # Setup project mock
            mock_project = Mock(spec=Project)
            mock_project.project_dir = project_dir
            mock_project.info.name = "test-project"
            mock_project.info.is_git_repo = True
            
            # .devcontainer doesn't exist
            devcontainer_path = project_dir / ".devcontainer"
            assert not devcontainer_path.exists()
            
            # Mock that .devcontainer is NOT in gitignore
            mock_is_gitignored.return_value = False
            
            # Create workspace manager
            workspace_mgr = WorkspaceManager(mock_project)
            
            # Call create_workspace with live=True
            result = workspace_mgr.create_workspace("test", live=True)
            
            # Should return the project directory (live mode)
            assert result == project_dir
            
            # Should have checked if .devcontainer is gitignored
            mock_is_gitignored.assert_called_once_with(project_dir)
            
            # Should NOT copy template since it's not gitignored
            mock_copytree.assert_not_called()