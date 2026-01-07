"""Shared pytest fixtures and utilities for devs CLI tests."""
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from devs_common.core.project import Project


@pytest.fixture(autouse=True)
def mock_check_dependencies():
    """Mock check_dependencies to prevent CLI from exiting due to missing tools."""
    with patch('devs.cli.check_dependencies'):
        yield


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client for testing container operations."""
    client = MagicMock()
    
    # Mock containers
    client.containers = MagicMock()
    client.containers.list = MagicMock(return_value=[])
    client.containers.get = MagicMock(side_effect=lambda name: Mock(
        name=name,
        status="running",
        attrs={"State": {"Running": True}},
        exec_run=MagicMock(return_value=(0, b"output"))
    ))
    
    # Mock images
    client.images = MagicMock()
    client.images.pull = MagicMock()
    client.images.list = MagicMock(return_value=[])
    
    # Mock networks
    client.networks = MagicMock()
    client.networks.list = MagicMock(return_value=[])
    
    return client


@pytest.fixture
def mock_subprocess():
    """Create a mock for subprocess operations."""
    mock = MagicMock()
    mock.run = MagicMock(return_value=Mock(
        returncode=0,
        stdout="Success",
        stderr=""
    ))
    mock.Popen = MagicMock(return_value=Mock(
        wait=MagicMock(return_value=0),
        communicate=MagicMock(return_value=(b"output", b""))
    ))
    return mock


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with devcontainer configuration."""
    project_path = tmp_path / "test-project"
    project_path.mkdir()

    # Initialize a proper git repository using git init
    subprocess.run(
        ['git', 'init'],
        cwd=project_path,
        capture_output=True,
        check=True
    )

    # Configure git user for commits
    subprocess.run(
        ['git', 'config', 'user.email', 'test@test.com'],
        cwd=project_path,
        capture_output=True,
        check=True
    )
    subprocess.run(
        ['git', 'config', 'user.name', 'Test User'],
        cwd=project_path,
        capture_output=True,
        check=True
    )

    # Add remote origin
    subprocess.run(
        ['git', 'remote', 'add', 'origin', 'https://github.com/test-org/test-repo.git'],
        cwd=project_path,
        capture_output=True,
        check=True
    )
    
    # Create .devcontainer directory
    devcontainer_dir = project_path / ".devcontainer"
    devcontainer_dir.mkdir()
    
    # Create devcontainer.json
    devcontainer_json = devcontainer_dir / "devcontainer.json"
    devcontainer_json.write_text("""{
    "name": "${localEnv:DEVCONTAINER_NAME:Default} - Test Project",
    "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
    "remoteEnv": {
        "GH_TOKEN": "${localEnv:GH_TOKEN}"
    }
}""")
    
    # Create some sample files
    (project_path / "README.md").write_text("# Test Project")
    (project_path / "main.py").write_text("print('Hello, World!')")
    
    return project_path


@pytest.fixture
def temp_project_no_git(tmp_path):
    """Create a temporary project without git but with devcontainer configuration."""
    project_path = tmp_path / "test-project-no-git"
    project_path.mkdir()
    
    # Create .devcontainer directory
    devcontainer_dir = project_path / ".devcontainer"
    devcontainer_dir.mkdir()
    
    # Create devcontainer.json
    devcontainer_json = devcontainer_dir / "devcontainer.json"
    devcontainer_json.write_text("""{
    "name": "Test Project No Git",
    "image": "mcr.microsoft.com/devcontainers/base:ubuntu"
}""")
    
    # Create some sample files
    (project_path / "README.md").write_text("# Test Project No Git")
    (project_path / "app.js").write_text("console.log('Hello');")
    
    return project_path


@pytest.fixture
def mock_project(temp_project):
    """Create a mock Project instance."""
    return Project(temp_project)


@pytest.fixture
def mock_container_manager(mock_docker_client, mock_project):
    """Create a mock ContainerManager instance with Docker mocked."""
    from unittest.mock import patch
    from devs_common.core.container import ContainerManager

    # Patch Docker before creating ContainerManager since __init__ connects to Docker
    with patch('devs_common.utils.docker_client.docker') as mock_docker_module:
        mock_docker_module.from_env.return_value = mock_docker_client
        mock_docker_client.ping = MagicMock()  # Add ping method for connection test

        manager = ContainerManager(mock_project)
        # Replace the docker attribute with our mock
        manager.docker.client = mock_docker_client
        yield manager


@pytest.fixture
def mock_workspace_manager(mock_project, tmp_path):
    """Create a mock WorkspaceManager instance."""
    from devs_common.core.workspace import WorkspaceManager
    from devs_common.config import BaseConfig

    # Create a mock config with the temp workspaces directory
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir(exist_ok=True)

    mock_config = MagicMock(spec=BaseConfig)
    mock_config.workspaces_dir = workspaces_dir
    mock_config.ensure_directories = MagicMock()

    manager = WorkspaceManager(mock_project, config=mock_config)
    # Also add workspaces_dir directly for tests that access it directly
    manager.workspaces_dir = workspaces_dir
    return manager


@pytest.fixture
def mock_vscode_integration(mock_project):
    """Create a mock VSCodeIntegration instance."""
    from devs.core.integration import VSCodeIntegration
    
    integration = VSCodeIntegration(mock_project)
    # Mock the subprocess calls
    integration._run_command = MagicMock(return_value=True)
    return integration


@pytest.fixture
def mock_external_tool_integration():
    """Create a mock ExternalToolIntegration instance."""
    from devs.core.integration import ExternalToolIntegration
    
    integration = ExternalToolIntegration()
    # Mock all tools as available by default
    integration.check_docker = MagicMock(return_value=True)
    integration.check_vscode = MagicMock(return_value=True)
    integration.check_devcontainer_cli = MagicMock(return_value=True)
    return integration


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables."""
    env_vars = {
        "DEVS_WORKSPACES_DIR": "/tmp/test-workspaces",
        "DEVS_PROJECT_PREFIX": "test",
        "GH_TOKEN": "test-github-token",
        "DEVCONTAINER_NAME": "test-container"
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture
def mock_container_response():
    """Create a mock container response for Docker API."""
    return {
        "Id": "abc123",
        "Name": "/dev-test-org-test-repo-alice",
        "State": {
            "Status": "running",
            "Running": True
        },
        "Config": {
            "Labels": {
                "devs.project": "test-org-test-repo",
                "devs.name": "alice"
            }
        }
    }


class MockContainer:
    """Mock Docker container for testing - matches ContainerInfo interface."""

    def __init__(self, name: str, status: str = "running", labels: Optional[Dict[str, str]] = None):
        from datetime import datetime
        self.name = name.lstrip("/")
        self.status = status
        self.labels = labels or {}
        self.created = datetime.now()
        self.id = f"mock-{name}"
        self.container_id = self.id
        # Extract dev_name and project_name from labels (like ContainerInfo does)
        self.dev_name = self.labels.get("devs.name", "unknown")
        self.project_name = self.labels.get("devs.project", "unknown")
        self.attrs = {
            "State": {
                "Status": status,
                "Running": status == "running"
            },
            "Config": {
                "Labels": self.labels
            }
        }
    
    def exec_run(self, cmd: str, **kwargs):
        """Mock exec_run method."""
        return (0, b"Mock output")
    
    def stop(self):
        """Mock stop method."""
        self.status = "exited"
        self.attrs["State"]["Status"] = "exited"
        self.attrs["State"]["Running"] = False
    
    def remove(self):
        """Mock remove method."""
        pass
    
    def reload(self):
        """Mock reload method."""
        pass
    
    def wait(self, condition="not-running", timeout=None):
        """Mock wait method."""
        return {"StatusCode": 0}


@pytest.fixture
def mock_containers():
    """Create a set of mock containers for testing."""
    return [
        MockContainer(
            "/dev-test-org-test-repo-alice",
            "running",
            {"devs.project": "test-org-test-repo", "devs.name": "alice"}
        ),
        MockContainer(
            "/dev-test-org-test-repo-bob",
            "running",
            {"devs.project": "test-org-test-repo", "devs.name": "bob"}
        ),
        MockContainer(
            "/dev-other-org-other-repo-charlie",
            "running",
            {"devs.project": "other-org-other-repo", "devs.name": "charlie"}
        )
    ]


@pytest.fixture
def capture_subprocess_calls():
    """Capture subprocess calls for verification."""
    calls = []
    
    def mock_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return Mock(returncode=0, stdout="", stderr="")
    
    return mock_run, calls