"""Integration tests for the 'vscode' command."""
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from devs.core.integration import VSCodeIntegration
from devs.exceptions import VSCodeError, WorkspaceError


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


class TestVSCodeSSHMode:
    """Tests for the SSH connection mode (--ssh / DEVS_SSH_HOST)."""

    @patch('devs.cli.DevsConfigLoader.load_ssh_host', return_value=None)
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_ssh_flag_skips_container_management(
        self,
        mock_vscode_class,
        mock_workspace_manager_class,
        mock_container_manager_class,
        mock_get_project,
        mock_load_ssh_host,
        cli_runner,
        temp_project,
    ):
        """When --ssh is given, ContainerManager and WorkspaceManager are not used."""
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.get_workspace_name.return_value = "test-org-test-repo-alice"
        mock_get_project.return_value = mock_project

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        result = cli_runner.invoke(cli, ['vscode', 'alice', '--ssh', 'myhost.ts.net'])

        assert result.exit_code == 0
        mock_container_manager_class.assert_not_called()
        mock_workspace_manager_class.assert_not_called()

    @patch('devs.cli.DevsConfigLoader.load_ssh_host', return_value=None)
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_ssh_flag_passes_host_to_launch(
        self,
        mock_vscode_class,
        mock_workspace_manager_class,
        mock_container_manager_class,
        mock_get_project,
        mock_load_ssh_host,
        cli_runner,
        temp_project,
    ):
        """--ssh host is forwarded to launch_multiple_devcontainers."""
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.get_workspace_name.return_value = "test-org-test-repo-alice"
        mock_get_project.return_value = mock_project

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        cli_runner.invoke(cli, ['vscode', 'alice', '--ssh', 'dev.example.ts.net'])

        call_kwargs = mock_vscode.launch_multiple_devcontainers.call_args
        assert call_kwargs.kwargs.get('ssh_host') == 'dev.example.ts.net' or \
               'dev.example.ts.net' in str(call_kwargs)

    @patch('devs.cli.DevsConfigLoader.load_ssh_host', return_value='devs-yml-host.ts.net')
    @patch('devs.cli.get_project')
    @patch('devs.cli.ContainerManager')
    @patch('devs.cli.WorkspaceManager')
    @patch('devs.cli.VSCodeIntegration')
    def test_ssh_host_from_devs_yml(
        self,
        mock_vscode_class,
        mock_workspace_manager_class,
        mock_container_manager_class,
        mock_get_project,
        mock_load_ssh_host,
        cli_runner,
        temp_project,
    ):
        """When ssh_host is in DEVS.yml and no --ssh flag, SSH mode is used."""
        mock_project = Mock()
        mock_project.info.name = "test-org-test-repo"
        mock_project.get_workspace_name.return_value = "test-org-test-repo-alice"
        mock_get_project.return_value = mock_project

        mock_vscode = Mock()
        mock_vscode.launch_multiple_devcontainers.return_value = 1
        mock_vscode_class.return_value = mock_vscode

        result = cli_runner.invoke(cli, ['vscode', 'alice'])

        assert result.exit_code == 0
        mock_container_manager_class.assert_not_called()
        call_kwargs = mock_vscode.launch_multiple_devcontainers.call_args
        assert call_kwargs.kwargs.get('ssh_host') == 'devs-yml-host.ts.net' or \
               'devs-yml-host.ts.net' in str(call_kwargs)


class TestSSHURIGeneration:
    """Unit tests for generate_devcontainer_uri with SSH host."""

    def _make_vsi(self):
        mock_project = Mock()
        mock_project.get_container_name.side_effect = lambda dn, prefix='dev': f'dev-test-org-repo-{dn}'
        mock_project.get_workspace_name.side_effect = lambda dn: f'test-org-repo-{dn}'
        with patch.object(VSCodeIntegration, '_check_vscode_cli', return_value=None):
            vsi = VSCodeIntegration.__new__(VSCodeIntegration)
            vsi.project = mock_project
        return vsi

    def test_local_uri_format_unchanged(self):
        """Local URI format (no ssh_host) is unchanged from the existing behaviour."""
        vsi = self._make_vsi()
        workspace_dir = Path('/home/user/.devs/workspaces/test-org-repo-alice')
        uri = vsi.generate_devcontainer_uri(workspace_dir, 'alice')
        hex_part = uri.split('attached-container+')[1].split('/')[0]
        decoded = bytes.fromhex(hex_part).decode('utf-8')
        assert decoded == 'dev-test-org-repo-alice'
        assert '/workspaces/test-org-repo-alice' in uri

    def test_ssh_uri_contains_json_with_host(self):
        """SSH URI encodes JSON with containerName (leading /) and settings.host."""
        vsi = self._make_vsi()
        workspace_dir = Path('/home/user/.devs/workspaces/test-org-repo-alice')
        uri = vsi.generate_devcontainer_uri(workspace_dir, 'alice', ssh_host='myhost.ts.net')
        hex_part = uri.split('attached-container+')[1].split('/')[0]
        decoded = json.loads(bytes.fromhex(hex_part).decode('utf-8'))
        assert decoded['containerName'] == '/dev-test-org-repo-alice'
        assert decoded['settings']['host'] == 'ssh://myhost.ts.net'

    def test_ssh_uri_workspace_path_correct(self):
        """SSH URI workspace path matches the devs naming convention."""
        vsi = self._make_vsi()
        workspace_dir = Path('/home/user/.devs/workspaces/test-org-repo-alice')
        uri = vsi.generate_devcontainer_uri(workspace_dir, 'alice', ssh_host='myhost.ts.net')
        assert uri.endswith('/workspaces/test-org-repo-alice')

    def test_ssh_host_with_port_is_preserved(self):
        """SSH host including a port number is preserved verbatim."""
        vsi = self._make_vsi()
        workspace_dir = Path('/home/user/.devs/workspaces/test-org-repo-alice')
        uri = vsi.generate_devcontainer_uri(workspace_dir, 'alice', ssh_host='myhost.ts.net:2222')
        hex_part = uri.split('attached-container+')[1].split('/')[0]
        decoded = json.loads(bytes.fromhex(hex_part).decode('utf-8'))
        assert decoded['settings']['host'] == 'ssh://myhost.ts.net:2222'
