"""Comprehensive tests for WorkspaceManager class."""
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from devs_common.core.workspace import WorkspaceManager
from devs_common.core.project import Project
from devs_common.config import BaseConfig
from devs_common.exceptions import WorkspaceError


class TestWorkspaceManager:
    """Test suite for WorkspaceManager class."""

    def test_init(self, mock_project, tmp_path):
        """Test WorkspaceManager initialization."""
        mock_config = MagicMock(spec=BaseConfig)
        mock_config.workspaces_dir = tmp_path / "workspaces"
        mock_config.ensure_directories = MagicMock()

        manager = WorkspaceManager(mock_project, config=mock_config)
        assert manager.project == mock_project
        assert manager.config == mock_config

    def test_init_custom_workspaces_dir(self, mock_project, tmp_path, monkeypatch):
        """Test WorkspaceManager with custom workspaces directory."""
        custom_dir = tmp_path / "custom-workspaces"

        mock_config = MagicMock(spec=BaseConfig)
        mock_config.workspaces_dir = custom_dir
        mock_config.ensure_directories = MagicMock()

        manager = WorkspaceManager(mock_project, config=mock_config)
        assert manager.config.workspaces_dir == custom_dir

    def test_get_workspace_dir(self, mock_workspace_manager):
        """Test workspace path generation."""
        path = mock_workspace_manager.get_workspace_dir("alice")
        assert path == mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"

    def test_workspace_exists_true(self, mock_workspace_manager):
        """Test checking if workspace exists (true case)."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        # Create a file so directory is not empty
        (workspace_path / "marker.txt").write_text("exists")

        exists = mock_workspace_manager.workspace_exists("alice")
        assert exists is True

    def test_workspace_exists_false(self, mock_workspace_manager):
        """Test checking if workspace exists (false case)."""
        exists = mock_workspace_manager.workspace_exists("alice")
        assert exists is False

    def test_create_workspace_git_project(self, mock_project, mock_workspace_manager, temp_project):
        """Test creating workspace for git project."""
        # The project is already a git repo from temp_project fixture
        # Create some additional files in the project
        src_dir = temp_project / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# Application code")

        # Create .gitignore
        gitignore = temp_project / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n.env\n")

        # Mock get_tracked_files to return tracked files
        with patch('devs_common.utils.git_utils.get_tracked_files') as mock_get_tracked:
            mock_get_tracked.return_value = [
                temp_project / "README.md",
                temp_project / "main.py",
                temp_project / "src" / "app.py",
                temp_project / ".gitignore"
            ]

            workspace_path = mock_workspace_manager.create_workspace("alice")

        # Verify workspace created
        assert workspace_path.exists()
        assert workspace_path == mock_workspace_manager.get_workspace_dir("alice")

    def test_create_workspace_non_git_project(self, mock_project, tmp_path):
        """Test creating workspace for non-git project (using mocks)."""
        from devs_common.core.workspace import WorkspaceManager
        from devs_common.core.project import ProjectInfo
        from devs_common.config import BaseConfig

        # Create a mock config
        workspaces_dir = tmp_path / "workspaces"
        workspaces_dir.mkdir(exist_ok=True)

        mock_config = MagicMock(spec=BaseConfig)
        mock_config.workspaces_dir = workspaces_dir
        mock_config.ensure_directories = MagicMock()

        # Create a fresh WorkspaceManager (don't use shared fixture)
        manager = WorkspaceManager(mock_project, config=mock_config)
        manager.workspaces_dir = workspaces_dir

        # Mock the ProjectInfo to indicate non-git repo
        # The _copy_all_files method is used for non-git projects
        mock_info = MagicMock(spec=ProjectInfo)
        mock_info.is_git_repo = False
        mock_info.name = "test-org-test-repo"

        with patch.object(type(manager.project), 'info', new_callable=lambda: property(lambda self: mock_info)):
            workspace_path = manager.create_workspace("alice")

        # Verify workspace created
        assert workspace_path.exists()

    def test_create_workspace_already_exists(self, mock_workspace_manager, temp_project):
        """Test creating workspace when it already exists."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "existing.txt").write_text("existing file")

        # Without reset_contents, should return existing workspace
        new_workspace_path = mock_workspace_manager.create_workspace("alice")

        assert new_workspace_path == workspace_path
        assert workspace_path.exists()
        # Old file should still exist (workspace was reused)
        assert (workspace_path / "existing.txt").exists()

    def test_create_workspace_with_reset(self, mock_workspace_manager, temp_project):
        """Test workspace creation with reset_contents flag."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "old_file.txt").write_text("old content")

        # With reset_contents=True, should clear contents
        new_workspace_path = mock_workspace_manager.create_workspace("alice", reset_contents=True)

        assert new_workspace_path == workspace_path
        assert workspace_path.exists()
        # Old file should be gone
        assert not (workspace_path / "old_file.txt").exists()

    def test_remove_workspace_exists(self, mock_workspace_manager):
        """Test removing existing workspace."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "file.txt").write_text("content")

        result = mock_workspace_manager.remove_workspace("alice")

        assert result is True
        assert not workspace_path.exists()

    def test_remove_workspace_not_exists(self, mock_workspace_manager):
        """Test removing non-existent workspace."""
        result = mock_workspace_manager.remove_workspace("alice")
        assert result is False

    def test_list_workspaces(self, mock_workspace_manager):
        """Test listing workspaces for current project."""
        # Create workspaces for current project
        alice_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"
        bob_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob"
        alice_path.mkdir(parents=True)
        bob_path.mkdir(parents=True)
        # Add marker files so directories aren't empty
        (alice_path / "marker.txt").write_text("alice")
        (bob_path / "marker.txt").write_text("bob")

        # Create workspace for different project
        other_path = mock_workspace_manager.workspaces_dir / "other-org-other-repo-charlie"
        other_path.mkdir(parents=True)
        (other_path / "marker.txt").write_text("charlie")

        workspaces = mock_workspace_manager.list_workspaces()

        assert len(workspaces) == 2
        assert "alice" in workspaces
        assert "bob" in workspaces
        assert "charlie" not in workspaces

    def test_cleanup_unused_workspaces(self, mock_workspace_manager):
        """Test cleaning unused workspaces."""
        # Create workspaces
        alice_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"
        bob_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob"
        alice_path.mkdir(parents=True)
        bob_path.mkdir(parents=True)
        (alice_path / "marker.txt").write_text("alice")
        (bob_path / "marker.txt").write_text("bob")

        # Only alice is active
        active_dev_names = {"alice"}

        removed = mock_workspace_manager.cleanup_unused_workspaces(active_dev_names)

        assert removed == 1  # bob was removed
        assert alice_path.exists()  # Active, should not be removed
        assert not bob_path.exists()  # Inactive, should be removed

    def test_workspace_exists_empty_directory(self, mock_workspace_manager):
        """Test that empty directory is not considered existing workspace."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        # Don't create any files - directory is empty

        exists = mock_workspace_manager.workspace_exists("alice")
        assert exists is False

    def test_create_workspace_live_mode(self, mock_workspace_manager, temp_project):
        """Test creating workspace in live mode returns project directory."""
        mock_workspace_manager.project.project_dir = temp_project

        with patch.object(mock_workspace_manager, '_copy_template_devcontainer_if_needed'):
            workspace_path = mock_workspace_manager.create_workspace("alice", live=True)

        # In live mode, should return the project directory itself
        assert workspace_path == temp_project

    def test_sync_workspace(self, mock_workspace_manager):
        """Test syncing workspace."""
        workspace_path = mock_workspace_manager.get_workspace_dir("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "marker.txt").write_text("exists")

        # Get the project directory from the manager itself
        project_dir = mock_workspace_manager.project.project_dir

        # Mock get_tracked_files to return tracked files
        with patch('devs_common.core.workspace.get_tracked_files') as mock_get_tracked:
            mock_get_tracked.return_value = [
                project_dir / "README.md",
                project_dir / "main.py"
            ]

            with patch('devs_common.core.workspace.copy_file_list'):
                result = mock_workspace_manager.sync_workspace("alice")

        assert result is True

    def test_sync_workspace_not_exists(self, mock_workspace_manager):
        """Test syncing non-existent workspace."""
        result = mock_workspace_manager.sync_workspace("nonexistent")
        assert result is False
