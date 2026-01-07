"""Comprehensive tests for ContainerManager class."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from devs_common.core.container import ContainerManager, ContainerInfo
from devs_common.core.project import Project
from devs_common.exceptions import ContainerError, DockerError
from tests.conftest import MockContainer


class TestContainerManager:
    """Test suite for ContainerManager class."""

    def test_init(self, mock_project):
        """Test ContainerManager initialization."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="@devcontainers/cli 0.70.0")

                manager = ContainerManager(mock_project)
                assert manager.project == mock_project
                assert manager.docker is not None

    def test_init_docker_not_available(self, mock_project):
        """Test ContainerManager initialization when Docker is not available."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            from docker.errors import DockerException
            mock_docker.from_env.side_effect = DockerException("Docker not found")

            with pytest.raises(DockerError) as exc_info:
                ContainerManager(mock_project)

            assert "Failed to connect to Docker" in str(exc_info.value)

    def test_get_container_info(self, mock_project):
        """Test _get_container_info method."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)
                info = manager._get_container_info("alice")

                assert "container_name" in info
                assert "workspace_name" in info
                assert "container_workspace_dir" in info
                assert "alice" in info["container_name"]

    def test_get_project_labels(self, mock_project):
        """Test _get_project_labels method."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)
                labels = manager._get_project_labels("alice")

                assert "devs.project" in labels
                assert "devs.dev" in labels
                assert labels["devs.dev"] == "alice"

    def test_get_project_labels_live_mode(self, mock_project):
        """Test _get_project_labels with live mode."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)
                labels = manager._get_project_labels("alice", live=True)

                assert labels.get("devs.live") == "true"

    def test_list_containers(self, mock_project):
        """Test listing containers for current project."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Mock find_containers_by_labels to return test containers
                manager.docker.find_containers_by_labels = MagicMock(return_value=[
                    {
                        'name': 'dev-test-org-test-repo-alice',
                        'id': 'abc123',
                        'status': 'running',
                        'labels': {'devs.project': 'test-org-test-repo', 'devs.dev': 'alice'},
                        'created': '2025-01-01T00:00:00.000000Z'
                    },
                    {
                        'name': 'dev-test-org-test-repo-bob',
                        'id': 'def456',
                        'status': 'running',
                        'labels': {'devs.project': 'test-org-test-repo', 'devs.dev': 'bob'},
                        'created': '2025-01-01T00:00:00.000000Z'
                    }
                ])

                containers = manager.list_containers()

                assert len(containers) == 2
                assert all(isinstance(c, ContainerInfo) for c in containers)
                assert {c.dev_name for c in containers} == {"alice", "bob"}

    def test_stop_container_success(self, mock_project):
        """Test successful container stop."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Mock find_containers_by_labels
                manager.docker.find_containers_by_labels = MagicMock(return_value=[
                    {
                        'name': 'dev-test-org-test-repo-alice',
                        'id': 'abc123',
                        'status': 'running',
                        'labels': {'devs.project': 'test-org-test-repo', 'devs.dev': 'alice'}
                    }
                ])
                manager.docker.stop_container = MagicMock()
                manager.docker.remove_container = MagicMock()

                result = manager.stop_container("alice")

                assert result is True
                manager.docker.stop_container.assert_called()
                manager.docker.remove_container.assert_called()

    def test_stop_container_not_found(self, mock_project):
        """Test stopping non-existent container."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Mock empty container list
                manager.docker.find_containers_by_labels = MagicMock(return_value=[])

                result = manager.stop_container("alice")

                assert result is False

    def test_should_rebuild_image_no_existing(self, mock_project):
        """Test should_rebuild_image when no image exists."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Mock no existing images
                manager.docker.find_images_by_pattern = MagicMock(return_value=[])

                should_rebuild, reason = manager.should_rebuild_image("alice")

                assert should_rebuild is False
                assert "No existing image" in reason

    def test_find_aborted_containers(self, mock_project):
        """Test finding aborted containers."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Mock containers in failed states
                manager.docker.find_containers_by_labels = MagicMock(return_value=[
                    {
                        'name': 'dev-test-org-test-repo-alice',
                        'id': 'abc123',
                        'status': 'exited',
                        'labels': {'devs.project': 'test-org-test-repo', 'devs.dev': 'alice', 'devs.managed': 'true'},
                        'created': '2025-01-01T00:00:00.000000Z'
                    }
                ])

                aborted = manager.find_aborted_containers()

                assert len(aborted) == 1
                assert aborted[0].status == 'exited'

    def test_remove_aborted_containers(self, mock_project):
        """Test removing aborted containers."""
        with patch('devs_common.utils.docker_client.docker') as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker.from_env.return_value = mock_docker_instance
            mock_docker_instance.ping.return_value = True

            with patch('devs_common.utils.devcontainer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                manager = ContainerManager(mock_project)

                # Create ContainerInfo objects for aborted containers
                aborted_containers = [
                    ContainerInfo(
                        name='dev-test-org-test-repo-alice',
                        dev_name='alice',
                        project_name='test-org-test-repo',
                        status='exited',
                        container_id='abc123'
                    )
                ]

                manager.docker.stop_container = MagicMock()
                manager.docker.remove_container = MagicMock()

                removed = manager.remove_aborted_containers(aborted_containers)

                assert removed == 1
                manager.docker.remove_container.assert_called_once()


class TestContainerInfo:
    """Test suite for ContainerInfo dataclass."""

    def test_container_info_creation(self):
        """Test ContainerInfo object creation."""
        from datetime import datetime

        info = ContainerInfo(
            name="dev-test-org-test-repo-alice",
            dev_name="alice",
            project_name="test-org-test-repo",
            status="running",
            container_id="abc123",
            created=datetime.now(),
            labels={"devs.project": "test-org-test-repo"}
        )

        assert info.name == "dev-test-org-test-repo-alice"
        assert info.dev_name == "alice"
        assert info.project_name == "test-org-test-repo"
        assert info.status == "running"
        assert info.container_id == "abc123"
        assert info.labels.get("devs.project") == "test-org-test-repo"

    def test_container_info_minimal(self):
        """Test ContainerInfo with minimal parameters."""
        info = ContainerInfo(
            name="test-container",
            dev_name="dev",
            project_name="project",
            status="running"
        )

        assert info.name == "test-container"
        assert info.container_id == ""
        assert info.created is None
        assert info.labels == {}
