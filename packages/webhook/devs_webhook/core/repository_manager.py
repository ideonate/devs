"""Repository management for webhook handler."""

import asyncio
import shutil
import time
from pathlib import Path
from typing import Optional, Dict
import structlog

from devs_common.utils.repo_cache import RepoCache

from ..config import get_config
from ..github.client import GitHubClient

logger = structlog.get_logger()


class RepositoryManager:
    """Manages repository cloning and caching for webhook tasks.

    Delegates actual git operations to the shared :class:`RepoCache` utility
    while adding async locking and cleanup on top.
    """

    def __init__(self):
        """Initialize repository manager."""
        self.config = get_config()

        self.github_client = GitHubClient(self.config)

        self.repo_cache = RepoCache(
            cache_dir=self.config.repo_cache_dir,
            token=self.config.github_token or None,
        )

        # Track repository status
        self.repo_locks: Dict[str, asyncio.Lock] = {}

        logger.info("Repository manager initialized",
                   cache_dir=str(self.config.repo_cache_dir))

    async def ensure_repository(
        self,
        repo_name: str,
        clone_url: str
    ) -> Optional[Path]:
        """Ensure repository is available locally and up to date.

        Args:
            repo_name: Repository name in format "owner/repo"
            clone_url: Repository clone URL (kept for API compatibility)

        Returns:
            Path to local repository or None if failed
        """
        # Get or create lock for this repository
        if repo_name not in self.repo_locks:
            self.repo_locks[repo_name] = asyncio.Lock()

        async with self.repo_locks[repo_name]:
            try:
                repo_dir = await asyncio.to_thread(
                    self.repo_cache.ensure_repo, repo_name
                )
                logger.info("Repository ready",
                           repo=repo_name, path=str(repo_dir))
                return repo_dir
            except Exception as e:
                logger.error("Failed to ensure repository",
                            repo=repo_name,
                            error=str(e))
                return None

    async def get_repository_info(self, repo_name: str) -> Optional[Dict]:
        """Get information about a repository.

        Args:
            repo_name: Repository name

        Returns:
            Repository info dict or None if not found
        """
        return await self.github_client.get_repository_info(repo_name)

    async def cleanup_old_repositories(self, max_age_days: int = 7) -> None:
        """Clean up old repository caches.

        Args:
            max_age_days: Maximum age in days before cleanup
        """
        try:
            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

            if not self.config.repo_cache_dir.exists():
                return

            for repo_dir in self.config.repo_cache_dir.iterdir():
                if repo_dir.is_dir():
                    # Check last modification time
                    mtime = repo_dir.stat().st_mtime

                    if mtime < cutoff_time:
                        logger.info("Cleaning up old repository cache",
                                   repo=repo_dir.name,
                                   age_days=(time.time() - mtime) / (24 * 60 * 60))
                        try:
                            shutil.rmtree(repo_dir)
                            logger.info("Repository removed", path=str(repo_dir))
                        except Exception as e:
                            logger.error("Failed to remove repository",
                                        path=str(repo_dir),
                                        error=str(e))

        except Exception as e:
            logger.error("Error during repository cleanup", error=str(e))
