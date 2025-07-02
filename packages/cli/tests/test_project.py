"""Tests for project detection and information."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from devs.core.project import Project, ProjectInfo
from devs.exceptions import DevcontainerConfigError


class TestProject:
    """Test cases for Project class."""
    
    def test_extract_project_name_from_ssh_url(self):
        """Test project name extraction from SSH git URLs."""
        project = Project()
        
        # SSH format
        result = project._extract_project_name_from_url("git@github.com:org/repo.git")
        assert result == "org-repo"
        
        # SSH without .git
        result = project._extract_project_name_from_url("git@github.com:org/repo")
        assert result == "org-repo"
    
    def test_extract_project_name_from_https_url(self):
        """Test project name extraction from HTTPS git URLs."""
        project = Project()
        
        # HTTPS format
        result = project._extract_project_name_from_url("https://github.com/org/repo.git")
        assert result == "org-repo"
        
        # HTTPS without .git
        result = project._extract_project_name_from_url("https://github.com/org/repo")
        assert result == "org-repo"
    
    def test_extract_project_name_invalid_url(self):
        """Test project name extraction from invalid URLs."""
        project = Project()
        
        result = project._extract_project_name_from_url("invalid-url")
        assert result == ""
        
        result = project._extract_project_name_from_url("")
        assert result == ""
    
    def test_get_container_name(self):
        """Test container name generation."""
        project = Project()
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
        project = Project()
        project._info = ProjectInfo(
            directory=Path("/test/project"),
            name="test-project", 
            git_remote_url="",
            hex_path="123abc",
            is_git_repo=False
        )
        
        result = project.get_workspace_name("sally")
        assert result == "project-sally"
    
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
    
    @patch('devs.core.project.Repo')
    def test_compute_project_info_with_git(self, mock_repo, tmp_path):
        """Test project info computation for git repository."""
        # Mock git repo
        mock_repo_instance = Mock()
        mock_repo_instance.remotes = [Mock()]
        mock_repo_instance.remotes.origin.url = "git@github.com:test/project.git"
        mock_repo.return_value = mock_repo_instance
        
        project = Project(tmp_path)
        info = project._compute_project_info()
        
        assert info.directory == tmp_path.resolve()
        assert info.name == "test-project"
        assert info.git_remote_url == "git@github.com:test/project.git"
        assert info.is_git_repo == True
    
    @patch('devs.core.project.Repo')
    def test_compute_project_info_without_git(self, mock_repo, tmp_path):
        """Test project info computation for non-git directory."""
        # Mock git repo to raise exception
        mock_repo.side_effect = Exception("Not a git repo")
        
        project = Project(tmp_path)
        info = project._compute_project_info()
        
        assert info.directory == tmp_path.resolve()
        assert info.name == tmp_path.name.lower()
        assert info.git_remote_url == ""
        assert info.is_git_repo == False