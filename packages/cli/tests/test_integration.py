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
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="1.85.0")
            integration = VSCodeIntegration(mock_project)
            assert integration.project == mock_project

    def test_init_vscode_not_found(self, mock_project):
        """Test VSCodeIntegration when VS Code not found."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(DependencyError) as exc_info:
                VSCodeIntegration(mock_project)
            assert "code" in str(exc_info.value)

    def test_generate_devcontainer_uri_attach(self, mock_project):
        """Test devcontainer URI generation for attaching to existing container."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            workspace_dir = Path("/tmp/workspace")
            uri = integration.generate_devcontainer_uri(
                workspace_dir, "alice", live=False, attach_to_existing=True
            )

            # Should use attached-container URI format
            assert uri.startswith("vscode-remote://attached-container+")
            assert "/workspaces/" in uri

    def test_generate_devcontainer_uri_new_container(self, mock_project):
        """Test devcontainer URI generation for creating new container."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            workspace_dir = Path("/tmp/workspace")
            uri = integration.generate_devcontainer_uri(
                workspace_dir, "alice", live=False, attach_to_existing=False
            )

            # Should use dev-container URI format
            assert uri.startswith("vscode-remote://dev-container+")
            assert "/workspaces/" in uri

    def test_generate_devcontainer_uri_live_mode(self, mock_project):
        """Test devcontainer URI generation in live mode."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            workspace_dir = Path("/tmp/myproject")
            uri = integration.generate_devcontainer_uri(
                workspace_dir, "alice", live=True, attach_to_existing=True
            )

            # In live mode, workspace name should be the folder name
            assert "/workspaces/myproject" in uri

    @patch('subprocess.Popen')
    def test_launch_devcontainer_success(self, mock_popen, mock_project):
        """Test successful VS Code launch."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            workspace_dir = Path("/tmp/workspace")
            workspace_dir = MagicMock(spec=Path)
            workspace_dir.name = "workspace"
            workspace_dir.as_posix.return_value = "/tmp/workspace"

            with patch('time.sleep'):
                result = integration.launch_devcontainer(workspace_dir, "alice")

            assert result is True
            mock_popen.assert_called_once()

    @patch('subprocess.Popen')
    def test_launch_devcontainer_failure(self, mock_popen, mock_project):
        """Test VS Code launch failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            mock_process = MagicMock()
            mock_process.poll.return_value = 1
            mock_process.returncode = 1
            mock_popen.return_value = mock_process

            workspace_dir = MagicMock(spec=Path)
            workspace_dir.name = "workspace"
            workspace_dir.as_posix.return_value = "/tmp/workspace"

            with patch('time.sleep'):
                with pytest.raises(VSCodeError):
                    integration.launch_devcontainer(workspace_dir, "alice")

    @patch('subprocess.Popen')
    def test_launch_multiple_devcontainers(self, mock_popen, mock_project):
        """Test launching multiple devcontainers."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            integration = VSCodeIntegration(mock_project)

            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            workspace1 = MagicMock(spec=Path)
            workspace1.name = "workspace1"
            workspace1.as_posix.return_value = "/tmp/workspace1"

            workspace2 = MagicMock(spec=Path)
            workspace2.name = "workspace2"
            workspace2.as_posix.return_value = "/tmp/workspace2"

            with patch('time.sleep'):
                count = integration.launch_multiple_devcontainers(
                    [workspace1, workspace2],
                    ["alice", "bob"],
                    delay_between_windows=0
                )

            assert count == 2


class TestExternalToolIntegration:
    """Test suite for ExternalToolIntegration class."""

    def test_init(self, mock_project):
        """Test ExternalToolIntegration initialization."""
        integration = ExternalToolIntegration(mock_project)
        assert integration.project == mock_project

    @patch('subprocess.run')
    def test_check_dependencies_all_available(self, mock_run, mock_project):
        """Test checking dependencies when all are available."""
        mock_run.return_value = Mock(returncode=0, stdout="version 1.0", stderr="")
        integration = ExternalToolIntegration(mock_project)

        status = integration.check_dependencies()

        assert 'docker' in status
        assert 'devcontainer' in status
        assert 'code' in status
        assert 'git' in status

        for tool in status.values():
            assert tool['available'] is True

    @patch('subprocess.run')
    def test_check_dependencies_some_missing(self, mock_run, mock_project):
        """Test checking dependencies when some are missing."""
        def side_effect(cmd, **kwargs):
            if 'docker' in cmd:
                raise FileNotFoundError()
            return Mock(returncode=0, stdout="version 1.0", stderr="")

        mock_run.side_effect = side_effect
        integration = ExternalToolIntegration(mock_project)

        status = integration.check_dependencies()

        assert status['docker']['available'] is False
        assert status['devcontainer']['available'] is True

    @patch('subprocess.run')
    def test_get_missing_dependencies_none_missing(self, mock_run, mock_project):
        """Test getting missing dependencies when all are available."""
        mock_run.return_value = Mock(returncode=0, stdout="version 1.0", stderr="")
        integration = ExternalToolIntegration(mock_project)

        missing = integration.get_missing_dependencies()

        assert len(missing) == 0

    @patch('subprocess.run')
    def test_get_missing_dependencies_some_missing(self, mock_run, mock_project):
        """Test getting missing dependencies when some are missing."""
        def side_effect(cmd, **kwargs):
            if 'docker' in cmd:
                raise FileNotFoundError()
            return Mock(returncode=0, stdout="version 1.0", stderr="")

        mock_run.side_effect = side_effect
        integration = ExternalToolIntegration(mock_project)

        missing = integration.get_missing_dependencies()

        assert 'docker' in missing
        assert 'devcontainer' not in missing

    @patch('subprocess.run')
    def test_print_dependency_status(self, mock_run, mock_project, capsys):
        """Test printing dependency status."""
        mock_run.return_value = Mock(returncode=0, stdout="version 1.0", stderr="")
        integration = ExternalToolIntegration(mock_project)

        # Just verify it doesn't crash - output goes to rich console
        integration.print_dependency_status()
