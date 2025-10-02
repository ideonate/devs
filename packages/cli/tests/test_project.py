"""Tests for project detection and information."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from devs_common.core.project import Project, ProjectInfo
from devs_common.exceptions import DevcontainerConfigError, ProjectNotFoundError


class TestProject:
    """Test cases for Project class."""
    
    def test_extract_project_name_from_ssh_url(self):
        """Test project name extraction from SSH git URLs."""
        # Create project without triggering git detection
        project = Project.__new__(Project)
        project.project_dir = Path.cwd()
        project._info = None
        
        # SSH format
        result = project._extract_project_name_from_url("git@github.com:org/repo.git")
        assert result == "org-repo"
        
        # SSH without .git
        result = project._extract_project_name_from_url("git@github.com:org/repo")
        assert result == "org-repo"
    
    def test_extract_project_name_from_https_url(self):
        """Test project name extraction from HTTPS git URLs."""
        # Create project without triggering git detection
        project = Project.__new__(Project)
        project.project_dir = Path.cwd()
        project._info = None
        
        # HTTPS format
        result = project._extract_project_name_from_url("https://github.com/org/repo.git")
        assert result == "org-repo"
        
        # HTTPS without .git
        result = project._extract_project_name_from_url("https://github.com/org/repo")
        assert result == "org-repo"
    
    def test_extract_project_name_invalid_url(self):
        """Test project name extraction from invalid URLs."""
        # Create project without triggering git detection
        project = Project.__new__(Project)
        project.project_dir = Path.cwd()
        project._info = None
        
        result = project._extract_project_name_from_url("invalid-url")
        assert result == ""
        
        result = project._extract_project_name_from_url("")
        assert result == ""
    
    def test_get_container_name(self):
        """Test container name generation."""
        # Create project without triggering git detection
        project = Project.__new__(Project)
        project.project_dir = Path.cwd()
        project._info = ProjectInfo(
            directory=Path("/test/project"),
            name="test-project",
            git_remote_url="",
            hex_path="123abc",
            is_git_repo=False
        )
        
        result = project.get_container_name("sally", "dev")
        assert result == "dev-test-project-sally"
    
    def test_get_workspace_name(self):
        """Test workspace name generation."""
        # Create project without triggering git detection
        project = Project.__new__(Project)
        project.project_dir = Path.cwd()
        project._info = ProjectInfo(
            directory=Path("/test/project"),
            name="test-project", 
            git_remote_url="",
            hex_path="123abc",
            is_git_repo=False
        )
        
        result = project.get_workspace_name("sally")
        assert result == "test-project-sally"
    
    def test_check_devcontainer_config_missing(self, tmp_path):
        """Test devcontainer config check when file is missing."""
        project = Project(tmp_path)
        
        with pytest.raises(DevcontainerConfigError):
            project.check_devcontainer_config()
    
    def test_check_devcontainer_config_exists(self, tmp_path):
        """Test devcontainer config check when file exists."""
        # Create devcontainer config
        devcontainer_dir = tmp_path / ".devcontainer"
        devcontainer_dir.mkdir()
        config_file = devcontainer_dir / "devcontainer.json"
        config_file.write_text('{"name": "test"}')
        
        project = Project(tmp_path)
        
        # Should not raise an exception
        project.check_devcontainer_config()
    
    @patch('devs_common.core.project.Repo')
    def test_compute_project_info_with_git(self, mock_repo, tmp_path):
        """Test project info computation for git repository."""
        # Mock git repo
        mock_repo_instance = Mock()
        
        # Mock the origin remote
        mock_origin = Mock()
        mock_origin.name = 'origin'
        mock_origin.url = "git@github.com:test/project.git"
        
        # Mock remotes collection
        mock_remotes = Mock()
        mock_remotes.__iter__ = Mock(return_value=iter([mock_origin]))
        mock_remotes.__bool__ = Mock(return_value=True)
        mock_remotes.origin = mock_origin
        
        mock_repo_instance.remotes = mock_remotes
        mock_repo.return_value = mock_repo_instance
        
        project = Project(tmp_path)
        info = project._compute_project_info()
        
        assert info.directory == tmp_path.resolve()
        assert info.name == "test-project"
        assert info.git_remote_url == "git@github.com:test/project.git"
        assert info.is_git_repo == True
    
    @patch('devs_common.core.project.Repo')
    def test_compute_project_info_without_git(self, mock_repo, tmp_path):
        """Test project info computation for non-git directory raises error."""
        # Mock git repo to raise InvalidGitRepositoryError
        from git.exc import InvalidGitRepositoryError
        mock_repo.side_effect = InvalidGitRepositoryError("Not a git repo")

        project = Project(tmp_path)

        # Should raise ProjectNotFoundError when not in a git repository
        with pytest.raises(ProjectNotFoundError) as exc_info:
            project._compute_project_info()

        assert "not a git repository" in str(exc_info.value)
        assert "requires a git repository" in str(exc_info.value)