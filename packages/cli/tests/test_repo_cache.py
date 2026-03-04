"""Tests for RepoCache utility and --repo CLI option."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest
from click.testing import CliRunner

from devs_common.utils.repo_cache import RepoCache


class TestRepoCache:
    """Unit tests for the RepoCache class."""

    def test_repo_name_to_dir_name(self):
        cache = RepoCache(cache_dir=Path("/tmp/cache"))
        assert cache._repo_name_to_dir_name("ideonate/devs") == "ideonate-devs"
        assert cache._repo_name_to_dir_name("Org/Repo") == "org-repo"

    def test_build_clone_url_no_token(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        cache = RepoCache()
        assert cache._build_clone_url("org/repo") == "https://github.com/org/repo.git"

    def test_build_clone_url_with_gh_token(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok123")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        cache = RepoCache()
        assert cache._build_clone_url("org/repo") == "https://tok123@github.com/org/repo.git"

    def test_build_clone_url_with_github_token(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "tok456")
        cache = RepoCache()
        assert cache._build_clone_url("org/repo") == "https://tok456@github.com/org/repo.git"

    @patch("devs_common.utils.repo_cache.subprocess.run")
    def test_ensure_repo_clones_when_missing(self, mock_run, tmp_path):
        cache = RepoCache(cache_dir=tmp_path)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        path = cache.ensure_repo("ideonate/devs")

        assert path == tmp_path / "ideonate-devs"
        # First call should be git clone
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0][0:2] == ["git", "clone"]

    @patch("devs_common.utils.repo_cache.subprocess.run")
    def test_ensure_repo_updates_when_exists(self, mock_run, tmp_path):
        # Pre-create repo directory with .git
        repo_dir = tmp_path / "ideonate-devs"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        mock_run.return_value = Mock(returncode=0, stdout="refs/remotes/origin/main", stderr="")
        cache = RepoCache(cache_dir=tmp_path)
        path = cache.ensure_repo("ideonate/devs")

        assert path == repo_dir
        # Should call set-url then fetch, not clone
        cmds = [c[0][0][:2] for c in mock_run.call_args_list]
        assert ["git", "remote"] in cmds
        assert ["git", "fetch"] in cmds

    @patch("devs_common.utils.repo_cache.subprocess.run")
    def test_ensure_repo_with_branch(self, mock_run, tmp_path):
        cache = RepoCache(cache_dir=tmp_path)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        cache.ensure_repo("org/repo", branch="develop")

        # Should have a checkout call with "develop"
        checkout_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][:2] == ["git", "checkout"]
        ]
        assert len(checkout_calls) >= 1
        assert "develop" in checkout_calls[0][0][0]

    @patch("devs_common.utils.repo_cache.subprocess.run")
    def test_clone_failure_raises(self, mock_run, tmp_path):
        from devs_common.exceptions import DevsError

        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: repo not found")
        cache = RepoCache(cache_dir=tmp_path)

        with pytest.raises(DevsError, match="Failed to clone"):
            cache.ensure_repo("bad/repo")


class TestRepoCliOption:
    """Test the --repo CLI option integration."""

    @patch("devs.cli.RepoCache")
    @patch("devs.cli.ContainerManager")
    @patch("devs.cli.WorkspaceManager")
    @patch("devs.cli.Project")
    def test_start_with_repo_flag(self, mock_project_cls, mock_wm, mock_cm, mock_rc):
        from devs.cli import cli

        # Set up mocks
        mock_cache_instance = MagicMock()
        mock_cache_instance.ensure_repo.return_value = Path("/tmp/cache/org-repo")
        mock_rc.return_value = mock_cache_instance

        mock_project = MagicMock()
        mock_project.info.name = "org-repo"
        mock_project_cls.return_value = mock_project

        mock_cm_instance = MagicMock()
        mock_cm_instance.ensure_container_running.return_value = True
        mock_cm.return_value = mock_cm_instance

        mock_wm_instance = MagicMock()
        mock_wm_instance.create_workspace.return_value = Path("/tmp/ws/org-repo-dev1")
        mock_wm.return_value = mock_wm_instance

        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", "org/repo", "start", "dev1"])

        # RepoCache should have been created and called
        mock_rc.assert_called_once()
        mock_cache_instance.ensure_repo.assert_called_once_with("org/repo")
        # Project should have been created with the cached repo path
        mock_project_cls.assert_called_with(project_dir=Path("/tmp/cache/org-repo"))

    @patch("devs.cli.Project")
    def test_start_without_repo_flag_uses_cwd(self, mock_project_cls):
        """Without --repo, Project() is called with no args (uses CWD)."""
        from devs.cli import cli

        mock_project = MagicMock()
        mock_project.info.name = "test-project"
        mock_project_cls.return_value = mock_project

        runner = CliRunner()
        # Will fail because of missing ContainerManager etc, but we check Project was called correctly
        with patch("devs.cli.ContainerManager") as mock_cm, \
             patch("devs.cli.WorkspaceManager") as mock_wm:
            mock_cm_instance = MagicMock()
            mock_cm_instance.ensure_container_running.return_value = True
            mock_cm.return_value = mock_cm_instance
            mock_wm_instance = MagicMock()
            mock_wm_instance.create_workspace.return_value = Path("/tmp/ws")
            mock_wm.return_value = mock_wm_instance

            result = runner.invoke(cli, ["start", "dev1"])

        # Project should be called without project_dir (defaults to CWD)
        mock_project_cls.assert_called_with()
