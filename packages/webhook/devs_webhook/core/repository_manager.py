"""Repository management for webhook handler."""

import asyncio
from pathlib import Path
from typing import Optional, Dict
import structlog

from ..config import get_config
from ..github.client import GitHubClient
from ..utils.async_utils import run_git_async

logger = structlog.get_logger()


class RepositoryManager:
    """Manages repository cloning and caching for webhook tasks."""
    
    def __init__(self):
        """Initialize repository manager."""
        self.config = get_config()
        
        self.github_client = GitHubClient(self.config)
        
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
            clone_url: Repository clone URL
            
        Returns:
            Path to local repository or None if failed
        """
        # Get or create lock for this repository
        if repo_name not in self.repo_locks:
            self.repo_locks[repo_name] = asyncio.Lock()
        
        async with self.repo_locks[repo_name]:
            return await self._ensure_repository_locked(repo_name, clone_url)
    
    async def _ensure_repository_locked(
        self, 
        repo_name: str, 
        clone_url: str
    ) -> Optional[Path]:
        """Ensure repository is available (called with lock held).
        
        Args:
            repo_name: Repository name
            clone_url: Repository clone URL
            
        Returns:
            Path to local repository or None if failed
        """
        # Calculate local path
        repo_dir = self.config.repo_cache_dir / repo_name.replace("/", "-")
        
        try:
            if repo_dir.exists():
                # Repository exists, update it
                logger.info("Updating existing repository", 
                           repo=repo_name, path=str(repo_dir))
                
                success = await self._update_repository(repo_dir)
                if success:
                    return repo_dir
                else:
                    # Update failed, try to reclone
                    logger.warning("Update failed, recloning repository",
                                  repo=repo_name)
                    await self._remove_repository(repo_dir)
            
            # Clone repository
            logger.info("Cloning repository", 
                       repo=repo_name, path=str(repo_dir))
            
            success = await self.github_client.clone_repository(
                repo_name, repo_dir
            )
            
            if success:
                return repo_dir
            else:
                return None
                
        except Exception as e:
            logger.error("Failed to ensure repository",
                        repo=repo_name,
                        error=str(e))
            return None
    
    async def _update_repository(self, repo_dir: Path) -> bool:
        """Update an existing repository.
        
        Args:
            repo_dir: Path to repository directory
            
        Returns:
            True if update successful
        """
        try:
            # Fetch all remotes using async git
            success, _, stderr = await run_git_async(
                ["fetch", "--all"],
                str(repo_dir)
            )
            
            if not success:
                logger.warning("Git fetch failed",
                              path=str(repo_dir),
                              error=stderr)
                return False
            
            # Reset to origin/main or origin/master
            for branch in ["main", "master"]:
                success, _, _ = await run_git_async(
                    ["reset", "--hard", f"origin/{branch}"],
                    str(repo_dir)
                )
                
                if success:
                    logger.info("Repository updated",
                               path=str(repo_dir),
                               branch=branch)
                    return True
            
            logger.warning("Could not reset to main or master branch",
                          path=str(repo_dir))
            return False
            
        except Exception as e:
            logger.error("Error updating repository",
                        path=str(repo_dir),
                        error=str(e))
            return False
    
    async def _remove_repository(self, repo_dir: Path) -> None:
        """Remove a repository directory.
        
        Args:
            repo_dir: Path to repository directory
        """
        try:
            import shutil
            shutil.rmtree(repo_dir)
            logger.info("Repository removed", path=str(repo_dir))
        except Exception as e:
            logger.error("Failed to remove repository",
                        path=str(repo_dir),
                        error=str(e))
    
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
            import time
            from datetime import datetime, timedelta
            
            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
            
            for repo_dir in self.config.repo_cache_dir.iterdir():
                if repo_dir.is_dir():
                    # Check last modification time
                    mtime = repo_dir.stat().st_mtime
                    
                    if mtime < cutoff_time:
                        logger.info("Cleaning up old repository cache",
                                   repo=repo_dir.name,
                                   age_days=(time.time() - mtime) / (24 * 60 * 60))
                        await self._remove_repository(repo_dir)
                        
        except Exception as e:
            logger.error("Error during repository cleanup", error=str(e))