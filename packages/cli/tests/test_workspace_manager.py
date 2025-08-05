"""Comprehensive tests for WorkspaceManager class."""
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from devs_common.core.workspace import WorkspaceManager
from devs_common.exceptions import WorkspaceError


class TestWorkspaceManager:
    """Test suite for WorkspaceManager class."""
    
    def test_init(self, mock_project):
        """Test WorkspaceManager initialization."""
        manager = WorkspaceManager(mock_project)
        assert manager.project == mock_project
        assert manager.workspaces_dir.exists()
    
    def test_init_custom_workspaces_dir(self, mock_project, tmp_path, monkeypatch):
        """Test WorkspaceManager with custom workspaces directory."""
        custom_dir = tmp_path / "custom-workspaces"
        monkeypatch.setenv("DEVS_WORKSPACES_DIR", str(custom_dir))
        
        manager = WorkspaceManager(mock_project)
        assert manager.workspaces_dir == custom_dir
        assert custom_dir.exists()
    
    def test_get_workspace_path(self, mock_workspace_manager):
        """Test workspace path generation."""
        path = mock_workspace_manager.get_workspace_path("alice")
        assert path == mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"
    
    def test_workspace_exists_true(self, mock_workspace_manager):
        """Test checking if workspace exists (true case)."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        exists = mock_workspace_manager.workspace_exists("alice")
        assert exists is True
    
    def test_workspace_exists_false(self, mock_workspace_manager):
        """Test checking if workspace exists (false case)."""
        exists = mock_workspace_manager.workspace_exists("alice")
        assert exists is False
    
    def test_create_workspace_git_project(self, mock_workspace_manager, temp_project):
        """Test creating workspace for git project."""
        # Create some additional files in the project
        src_dir = temp_project / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# Application code")
        
        # Create .gitignore
        gitignore = temp_project / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n.env\n")
        
        # Create ignored files
        (temp_project / "test.pyc").write_text("compiled")
        cache_dir = temp_project / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "test.cpython-39.pyc").write_text("cache")
        
        # Mock git ls-files to return tracked files
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="README.md\nmain.py\nsrc/app.py\n.gitignore\n",
                stderr=""
            )
            
            workspace_path = mock_workspace_manager.create_workspace("alice")
        
        # Verify workspace created
        assert workspace_path.exists()
        assert workspace_path == mock_workspace_manager.get_workspace_path("alice")
        
        # Verify tracked files copied
        assert (workspace_path / "README.md").exists()
        assert (workspace_path / "main.py").exists()
        assert (workspace_path / "src" / "app.py").exists()
        assert (workspace_path / ".gitignore").exists()
        
        # Verify ignored files not copied
        assert not (workspace_path / "test.pyc").exists()
        assert not (workspace_path / "__pycache__").exists()
        
        # Verify special directories copied
        assert (workspace_path / ".git").exists()
        assert (workspace_path / ".devcontainer").exists()
    
    def test_create_workspace_non_git_project(self, mock_workspace_manager, temp_project_no_git):
        """Test creating workspace for non-git project."""
        # Change project path to non-git project
        mock_workspace_manager.project.path = temp_project_no_git
        
        # Create some additional files
        (temp_project_no_git / "src").mkdir()
        (temp_project_no_git / "src" / "index.js").write_text("console.log('app');")
        
        # Create directories that should be excluded
        node_modules = temp_project_no_git / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("{}")
        
        build_dir = temp_project_no_git / "build"
        build_dir.mkdir()
        (build_dir / "output.js").write_text("built")
        
        workspace_path = mock_workspace_manager.create_workspace("alice")
        
        # Verify workspace created
        assert workspace_path.exists()
        
        # Verify files copied
        assert (workspace_path / "README.md").exists()
        assert (workspace_path / "app.js").exists()
        assert (workspace_path / "src" / "index.js").exists()
        assert (workspace_path / ".devcontainer").exists()
        
        # Verify excluded directories not copied
        assert not (workspace_path / "node_modules").exists()
        assert not (workspace_path / "build").exists()
    
    def test_create_workspace_already_exists(self, mock_workspace_manager):
        """Test creating workspace when it already exists."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "existing.txt").write_text("existing file")
        
        # Should remove existing and create new
        new_workspace_path = mock_workspace_manager.create_workspace("alice")
        
        assert new_workspace_path == workspace_path
        assert workspace_path.exists()
        # Old file should be gone (workspace was recreated)
        assert not (workspace_path / "existing.txt").exists()
    
    def test_create_workspace_copy_error(self, mock_workspace_manager, temp_project):
        """Test workspace creation with copy error."""
        with patch('shutil.copytree') as mock_copytree:
            mock_copytree.side_effect = OSError("Permission denied")
            
            with pytest.raises(WorkspaceError) as exc_info:
                mock_workspace_manager.create_workspace("alice")
            
            assert "Failed to create workspace" in str(exc_info.value)
    
    def test_remove_workspace_exists(self, mock_workspace_manager):
        """Test removing existing workspace."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        (workspace_path / "file.txt").write_text("content")
        
        result = mock_workspace_manager.remove_workspace("alice")
        
        assert result is True
        assert not workspace_path.exists()
    
    def test_remove_workspace_not_exists(self, mock_workspace_manager):
        """Test removing non-existent workspace."""
        result = mock_workspace_manager.remove_workspace("alice")
        assert result is False
    
    def test_remove_workspace_error(self, mock_workspace_manager):
        """Test workspace removal with error."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = OSError("Permission denied")
            
            with pytest.raises(WorkspaceError) as exc_info:
                mock_workspace_manager.remove_workspace("alice")
            
            assert "Failed to remove workspace" in str(exc_info.value)
    
    def test_list_workspaces(self, mock_workspace_manager):
        """Test listing workspaces for current project."""
        # Create workspaces for current project
        (mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice").mkdir(parents=True)
        (mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob").mkdir(parents=True)
        
        # Create workspace for different project
        (mock_workspace_manager.workspaces_dir / "other-org-other-repo-charlie").mkdir(parents=True)
        
        workspaces = mock_workspace_manager.list_workspaces()
        
        assert len(workspaces) == 2
        assert "alice" in workspaces
        assert "bob" in workspaces
        assert "charlie" not in workspaces
    
    def test_list_all_workspaces(self, mock_workspace_manager):
        """Test listing all workspaces."""
        # Create various workspaces
        (mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice").mkdir(parents=True)
        (mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob").mkdir(parents=True)
        (mock_workspace_manager.workspaces_dir / "other-org-other-repo-charlie").mkdir(parents=True)
        
        # Create a non-workspace directory (should be ignored)
        (mock_workspace_manager.workspaces_dir / "not-a-workspace").mkdir(parents=True)
        
        all_workspaces = mock_workspace_manager.list_all_workspaces()
        
        assert len(all_workspaces) == 3
        expected = [
            ("test-org-test-repo", "alice"),
            ("test-org-test-repo", "bob"),
            ("other-org-other-repo", "charlie")
        ]
        assert sorted(all_workspaces) == sorted(expected)
    
    def test_clean_project_workspaces(self, mock_workspace_manager):
        """Test cleaning workspaces for current project."""
        # Create workspaces
        alice_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"
        bob_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob"
        other_path = mock_workspace_manager.workspaces_dir / "other-org-other-repo-charlie"
        
        alice_path.mkdir(parents=True)
        bob_path.mkdir(parents=True)
        other_path.mkdir(parents=True)
        
        removed = mock_workspace_manager.clean_project_workspaces()
        
        assert removed == ["alice", "bob"]
        assert not alice_path.exists()
        assert not bob_path.exists()
        assert other_path.exists()  # Should not be removed
    
    def test_clean_unused_workspaces(self, mock_workspace_manager):
        """Test cleaning unused workspaces."""
        # Create workspaces
        alice_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-alice"
        bob_path = mock_workspace_manager.workspaces_dir / "test-org-test-repo-bob"
        alice_path.mkdir(parents=True)
        bob_path.mkdir(parents=True)
        
        # Mock active containers (only alice is active)
        active_containers = [("test-org-test-repo", "alice")]
        
        removed = mock_workspace_manager.clean_unused_workspaces(active_containers)
        
        assert removed == [("test-org-test-repo", "bob")]
        assert alice_path.exists()  # Active, should not be removed
        assert not bob_path.exists()  # Inactive, should be removed
    
    def test_get_workspace_size(self, mock_workspace_manager):
        """Test getting workspace size."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        # Create some files with known sizes
        (workspace_path / "file1.txt").write_text("Hello" * 100)  # 500 bytes
        (workspace_path / "file2.txt").write_text("World" * 200)  # 1000 bytes
        
        subdir = workspace_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("Test" * 250)  # 1000 bytes
        
        size = mock_workspace_manager.get_workspace_size("alice")
        
        # Size should be approximately 2500 bytes (may vary slightly by filesystem)
        assert 2000 < size < 3000
    
    def test_get_workspace_size_not_exists(self, mock_workspace_manager):
        """Test getting size of non-existent workspace."""
        size = mock_workspace_manager.get_workspace_size("alice")
        assert size == 0
    
    def test_copy_additional_files(self, mock_workspace_manager, temp_project):
        """Test copying additional files to workspace."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        # Create a file to copy
        extra_file = temp_project / "extra.txt"
        extra_file.write_text("Extra content")
        
        mock_workspace_manager.copy_additional_files("alice", [extra_file])
        
        assert (workspace_path / "extra.txt").exists()
        assert (workspace_path / "extra.txt").read_text() == "Extra content"
    
    def test_sync_workspace_changes(self, mock_workspace_manager, temp_project):
        """Test syncing changes from workspace back to project."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        # Create a modified file in workspace
        (workspace_path / "modified.txt").write_text("Modified content")
        
        # Create a file to sync
        (temp_project / "modified.txt").write_text("Original content")
        
        with patch('subprocess.run') as mock_run:
            # Mock rsync command
            mock_run.return_value = Mock(returncode=0)
            
            mock_workspace_manager.sync_workspace_changes("alice", ["modified.txt"])
            
            # Verify rsync was called with correct arguments
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "rsync" in cmd
            assert str(workspace_path) in " ".join(cmd)
            assert str(temp_project) in " ".join(cmd)
    
    def test_get_workspace_info(self, mock_workspace_manager):
        """Test getting workspace information."""
        workspace_path = mock_workspace_manager.get_workspace_path("alice")
        workspace_path.mkdir(parents=True)
        
        # Create some files
        (workspace_path / "file1.txt").write_text("Content")
        (workspace_path / "file2.txt").write_text("More content")
        
        info = mock_workspace_manager.get_workspace_info("alice")
        
        assert info["name"] == "alice"
        assert info["path"] == workspace_path
        assert info["exists"] is True
        assert info["size"] > 0
        assert "created" in info
        assert "modified" in info