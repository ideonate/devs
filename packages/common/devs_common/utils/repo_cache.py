"""Repository cache for cloning GitHub repos locally."""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from ..exceptions import DevsError
from .console import get_console

console = get_console()


class RepoCache:
    """Manages a local cache of cloned GitHub repositories.

    Repos are cloned into a cache directory (default: ~/.devs/repocache/)
    using the naming convention org-repo (e.g. ideonate-devs).
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = cache_dir or Path.home() / ".devs" / "repocache"

    def _repo_name_to_dir_name(self, repo_name: str) -> str:
        """Convert org/repo to org-repo directory name."""
        return repo_name.replace("/", "-").lower()

    def _build_clone_url(self, repo_name: str) -> str:
        """Build clone URL, using GH_TOKEN if available for private repos."""
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            return f"https://{token}@github.com/{repo_name}.git"
        return f"https://github.com/{repo_name}.git"

    def ensure_repo(self, repo_name: str, branch: Optional[str] = None) -> Path:
        """Ensure a repository is cloned and up-to-date in the cache.

        Args:
            repo_name: GitHub repo in org/repo format (e.g. "ideonate/devs")
            branch: Optional branch to checkout. Defaults to repo's default branch.

        Returns:
            Path to the cached repository directory.

        Raises:
            DevsError: If cloning or updating fails.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        dir_name = self._repo_name_to_dir_name(repo_name)
        repo_path = self.cache_dir / dir_name

        if repo_path.exists() and (repo_path / ".git").exists():
            self._update_repo(repo_path, repo_name, branch)
        else:
            self._clone_repo(repo_path, repo_name, branch)

        return repo_path

    def _clone_repo(self, repo_path: Path, repo_name: str, branch: Optional[str] = None) -> None:
        """Clone a repository into the cache."""
        # Remove directory if it exists but isn't a valid git repo
        if repo_path.exists():
            shutil.rmtree(repo_path)

        clone_url = self._build_clone_url(repo_name)
        console.print(f"   Cloning {repo_name} into cache...")

        cmd = ["git", "clone", clone_url, str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise DevsError(
                f"Failed to clone {repo_name}: {result.stderr.strip()}"
            )

        if branch:
            self._checkout_branch(repo_path, branch)

    def _update_repo(self, repo_path: Path, repo_name: str, branch: Optional[str] = None) -> None:
        """Fetch latest changes for an existing cached repo."""
        console.print(f"   Updating cached repo {repo_name}...")

        # Update remote URL in case token changed
        clone_url = self._build_clone_url(repo_name)
        subprocess.run(
            ["git", "remote", "set-url", "origin", clone_url],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        result = subprocess.run(
            ["git", "fetch", "--all"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Fetch failed – re-clone from scratch
            console.print(f"   Fetch failed, re-cloning {repo_name}...")
            self._clone_repo(repo_path, repo_name, branch)
            return

        # Checkout the requested branch (or default)
        target = branch or self._get_default_branch(repo_path)
        if target:
            self._checkout_branch(repo_path, target)

    def _checkout_branch(self, repo_path: Path, branch: str) -> None:
        """Checkout a specific branch, pulling latest changes."""
        result = subprocess.run(
            ["git", "checkout", "-f", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise DevsError(
                f"Failed to checkout branch '{branch}': {result.stderr.strip()}"
            )

        # Pull latest for this branch
        subprocess.run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

    def _get_default_branch(self, repo_path: Path) -> Optional[str]:
        """Detect the default branch of a repo (main or master)."""
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Output like "refs/remotes/origin/main"
            ref = result.stdout.strip()
            return ref.split("/")[-1]

        # Fallback: try common branch names
        for branch in ("main", "master"):
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return branch

        return None
