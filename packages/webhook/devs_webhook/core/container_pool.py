"""Container pool management for webhook tasks."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Any
from pathlib import Path
import structlog

from devs.core.project import Project
from devs.core.container import ContainerManager
from devs.core.workspace import WorkspaceManager

from ..config import get_config

logger = structlog.get_logger()


class ContainerPool:
    """Manages a pool of named containers for webhook tasks."""
    
    def __init__(self):
        """Initialize container pool."""
        self.config = get_config()
        
        # Track container status
        self.available_containers: Set[str] = set(self.config.container_pool)
        self.busy_containers: Dict[str, Dict[str, Any]] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info("Container pool initialized", 
                   containers=self.config.container_pool)
    
    async def allocate_container(
        self, 
        repo_name: str, 
        repo_path: Path
    ) -> Optional[str]:
        """Allocate a container for a task.
        
        Args:
            repo_name: Repository name (owner/repo)
            repo_path: Path to repository on host
            
        Returns:
            Container name if allocated, None if none available
        """
        async with self._lock:
            # Clean up expired containers first
            await self._cleanup_expired_containers()
            
            if not self.available_containers:
                logger.warning("No available containers", 
                              available=len(self.available_containers),
                              busy=len(self.busy_containers))
                return None
            
            # Get next available container (round-robin)
            container_name = self.available_containers.pop()
            
            # Set up container for this repository
            try:
                success = await self._setup_container(
                    container_name, repo_name, repo_path
                )
                
                if not success:
                    # Return container to available pool
                    self.available_containers.add(container_name)
                    return None
                
                # Mark as busy
                self.busy_containers[container_name] = {
                    "repo_name": repo_name,
                    "repo_path": str(repo_path),
                    "allocated_at": datetime.now(),
                    "expires_at": datetime.now() + timedelta(
                        minutes=self.config.container_timeout_minutes
                    )
                }
                
                logger.info("Container allocated",
                           container=container_name,
                           repo=repo_name,
                           expires_in_minutes=self.config.container_timeout_minutes)
                
                return container_name
                
            except Exception as e:
                # Return container to available pool on error
                self.available_containers.add(container_name)
                logger.error("Failed to setup container",
                            container=container_name,
                            repo=repo_name,
                            error=str(e))
                return None
    
    async def release_container(self, container_name: str) -> None:
        """Release a container back to the available pool.
        
        Args:
            container_name: Name of container to release
        """
        async with self._lock:
            if container_name in self.busy_containers:
                # Clean up container
                await self._cleanup_container(container_name)
                
                # Move back to available
                del self.busy_containers[container_name]
                self.available_containers.add(container_name)
                
                logger.info("Container released", container=container_name)
            else:
                logger.warning("Attempted to release unknown container",
                              container=container_name)
    
    async def force_stop_container(self, container_name: str) -> bool:
        """Force stop a container.
        
        Args:
            container_name: Name of container to stop
            
        Returns:
            True if stopped successfully
        """
        async with self._lock:
            if container_name in self.busy_containers:
                await self._cleanup_container(container_name)
                del self.busy_containers[container_name]
                self.available_containers.add(container_name)
                
                logger.info("Container force stopped", container=container_name)
                return True
            
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current pool status."""
        async with self._lock:
            return {
                "available": list(self.available_containers),
                "busy": {
                    name: {
                        "repo": info["repo_name"],
                        "allocated_at": info["allocated_at"].isoformat(),
                        "expires_at": info["expires_at"].isoformat(),
                    }
                    for name, info in self.busy_containers.items()
                },
                "total_containers": len(self.config.container_pool),
            }
    
    async def _setup_container(
        self, 
        container_name: str, 
        repo_name: str, 
        repo_path: Path
    ) -> bool:
        """Set up a container for a repository.
        
        Args:
            container_name: Name of container to set up
            repo_name: Repository name
            repo_path: Path to repository
            
        Returns:
            True if setup successful
        """
        try:
            # Create a temporary project for this repo
            project = Project(repo_path)
            
            # Set up workspace manager with webhook workspace dir
            workspace_manager = WorkspaceManager(project)
            workspace_manager.config.workspaces_dir = self.config.workspace_dir
            
            # Create workspace for this container
            workspace_dir = workspace_manager.create_workspace(
                container_name, force=True  # Always recreate for fresh start
            )
            
            # Set up container manager
            container_manager = ContainerManager(project)
            
            # Ensure container is running
            success = container_manager.ensure_container_running(
                container_name, workspace_dir, force_rebuild=False
            )
            
            if success:
                logger.info("Container setup complete",
                           container=container_name,
                           repo=repo_name,
                           workspace=str(workspace_dir))
            
            return success
            
        except Exception as e:
            logger.error("Container setup failed",
                        container=container_name,
                        repo=repo_name,
                        error=str(e))
            return False
    
    async def _cleanup_container(self, container_name: str) -> None:
        """Clean up a container after use.
        
        Args:
            container_name: Name of container to clean up
        """
        try:
            # Get container info
            container_info = self.busy_containers.get(container_name)
            if not container_info:
                return
            
            repo_path = Path(container_info["repo_path"])
            
            # Create project and managers for cleanup
            project = Project(repo_path)
            
            workspace_manager = WorkspaceManager(project)
            workspace_manager.config.workspaces_dir = self.config.workspace_dir
            
            container_manager = ContainerManager(project)
            
            # Stop container
            container_manager.stop_container(container_name)
            
            # Remove workspace
            workspace_manager.remove_workspace(container_name)
            
            logger.info("Container cleanup complete", container=container_name)
            
        except Exception as e:
            logger.error("Container cleanup failed",
                        container=container_name,
                        error=str(e))
    
    async def _cleanup_expired_containers(self) -> None:
        """Clean up containers that have exceeded their timeout."""
        now = datetime.now()
        expired_containers = []
        
        for container_name, info in self.busy_containers.items():
            if now > info["expires_at"]:
                expired_containers.append(container_name)
        
        for container_name in expired_containers:
            logger.info("Container expired, cleaning up",
                       container=container_name)
            await self._cleanup_container(container_name)
            del self.busy_containers[container_name]
            self.available_containers.add(container_name)