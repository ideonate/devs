"""Repository cache for cloning GitHub repos locally."""

import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional

from ..exceptions import DevsError
from .console import get_console

console = get_console()


class RepoCache:
    """Manages a local cache of cloned GitHub repositories.

    Repos are cloned into a cache directory (default: ~/.devs/repocache/)
    using the naming convention org-repo (e.g. ideonate-devs).

    Args:
        cache_dir: Directory for cached repos. Defaults to ~/.devs/repocache/.
        token: GitHub token for private repo access. If not provided, falls
            back to GH_TOKEN / GITHUB_TOKEN environment variables.
        default_branches: Ordered list of branch names to try when no explicit
            branch is requested. Defaults to detecting via symbolic-ref, then
            trying "main" and "master".
        clean: If True, run ``git clean -fd`` after checkout to remove
            untracked files from previous runs.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        token: Optional[str] = None,
        default_branches: Optional[List[str]] = None,
        clean: bool = False,
    ) -> None:
        self.cache_dir = cache_dir or Path.home() / ".devs" / "repocache"
        self._token = token
        self._default_branches = default_branches
        self._clean = clean

    def _repo_name_to_dir_name(self, repo_name: str) -> str:
        """Convert org/repo to org-repo directory name."""
        return repo_name.replace("/", "-").lower()

    def _get_token(self) -> Optional[str]:
        """Return the configured token, falling back to environment variables."""
        if self._token:
            return self._token
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _build_clone_url(self, repo_name: str) -> str:
        """Build clone URL, using token if available for private repos."""
        token = self._get_token()
        if token:
            return f"https://x-access-token:{token}@github.com/{repo_name}.git"
        return f"https://github.com/{repo_name}.git"

    def get_repo_path(self, repo_name: str) -> Path:
        """Return the local cache path for a repo without cloning.

        Args:
            repo_name: GitHub repo in org/repo format.

        Returns:
            Path where the repo would be cached.
        """
        return self.cache_dir / self._repo_name_to_dir_name(repo_name)

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

        repo_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone", clone_url, str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise DevsError(
                f"Failed to clone {repo_name}: {result.stderr.strip()}"
            )

        target = branch or self._detect_branch(repo_path)
        if target:
            self._checkout_branch(repo_path, target)

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
        target = branch or self._detect_branch(repo_path)
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

        # Reset to match remote so we pick up fetched changes
        subprocess.run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if self._clean:
            self._clean_untracked(repo_path)

    def _clean_untracked(self, repo_path: Path) -> None:
        """Remove untracked files and directories from the repo."""
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

    def _detect_branch(self, repo_path: Path) -> Optional[str]:
        """Detect the default branch to checkout.

        If ``default_branches`` was provided at construction, tries each in
        order. Otherwise falls back to symbolic-ref detection then main/master.
        """
        if self._default_branches:
            for branch in self._default_branches:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"origin/{branch}"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return branch
            return None

        return self._get_default_branch(repo_path)

    def _get_default_branch(self, repo_path: Path) -> Optional[str]:
        """Detect the default branch of a repo (main or master)."""
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
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
