"""Container pool management for webhook tasks."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Any, NamedTuple
from pathlib import Path
import structlog

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager

from ..config import get_config
from .webhook_config import WebhookConfig
from ..github.models import WebhookEvent
from .claude_dispatcher import ClaudeDispatcher, TaskResult

logger = structlog.get_logger()


class QueuedTask(NamedTuple):
    """A task queued for execution in a container."""
    task_id: str
    repo_name: str
    task_description: str
    event: WebhookEvent
    workspace_name: str


class ContainerPool:
    """Manages a pool of named containers for webhook tasks."""
    
    def __init__(self):
        """Initialize container pool."""
        self.config = get_config()
        self.claude_dispatcher = ClaudeDispatcher()
        
        # Track container status
        self.available_containers: Set[str] = set(self.config.container_pool)
        self.busy_containers: Dict[str, Dict[str, Any]] = {}
        
        # Task queues - one per container
        self.container_queues: Dict[str, asyncio.Queue] = {
            container: asyncio.Queue() for container in self.config.container_pool
        }
        
        # Container workers - one per container
        self.container_workers: Dict[str, asyncio.Task] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Start worker tasks for each container
        self._start_workers()
        
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
    
    async def queue_task(
        self,
        task_id: str,
        repo_name: str,
        task_description: str,
        event: WebhookEvent,
        workspace_name: str
    ) -> bool:
        """Queue a task for execution in the next available container.
        
        Args:
            task_id: Unique task identifier
            repo_name: Repository name (owner/repo)
            task_description: Task description for Claude
            event: Original webhook event
            workspace_name: Workspace directory name
            
        Returns:
            True if task was queued successfully
        """
        try:
            # Find container with shortest queue
            best_container = None
            min_queue_size = float('inf')
            
            for container_name in self.config.container_pool:
                queue_size = self.container_queues[container_name].qsize()
                if queue_size < min_queue_size:
                    min_queue_size = queue_size
                    best_container = container_name
            
            if best_container is None:
                logger.error("No containers available for task queuing")
                return False
            
            # Create queued task
            queued_task = QueuedTask(
                task_id=task_id,
                repo_name=repo_name,
                task_description=task_description,
                event=event,
                workspace_name=workspace_name
            )
            
            # Add to queue
            await self.container_queues[best_container].put(queued_task)
            
            logger.info("Task queued successfully",
                       task_id=task_id,
                       container=best_container,
                       queue_size=min_queue_size + 1,
                       repo=repo_name)
            
            return True
            
        except Exception as e:
            logger.error("Failed to queue task",
                        task_id=task_id,
                        error=str(e))
            return False
    
    def _start_workers(self) -> None:
        """Start worker tasks for each container."""
        for container_name in self.config.container_pool:
            worker_task = asyncio.create_task(
                self._container_worker(container_name)
            )
            self.container_workers[container_name] = worker_task
            
            logger.info("Started worker for container", container=container_name)
    
    async def _container_worker(self, container_name: str) -> None:
        """Worker process for a specific container.
        
        Args:
            container_name: Name of the container this worker manages
        """
        logger.info("Container worker started", container=container_name)
        
        try:
            while True:
                # Wait for a task from the queue
                try:
                    queued_task = await self.container_queues[container_name].get()
                    
                    logger.info("Worker processing task",
                               container=container_name,
                               task_id=queued_task.task_id,
                               repo=queued_task.repo_name)
                    
                    # Process the task
                    await self._process_task(container_name, queued_task)
                    
                    # Mark task as done
                    self.container_queues[container_name].task_done()
                    
                except asyncio.CancelledError:
                    logger.info("Container worker cancelled", container=container_name)
                    break
                except Exception as e:
                    logger.error("Error in container worker",
                                container=container_name,
                                error=str(e))
                    # Continue processing other tasks
                    continue
                    
        except Exception as e:
            logger.error("Container worker failed",
                        container=container_name,
                        error=str(e))
    
    async def _process_task(self, container_name: str, queued_task: QueuedTask) -> None:
        """Process a single task in a container.
        
        Args:
            container_name: Name of container to execute in
            queued_task: Task to process
        """
        try:
            # Setup container for the repository if needed
            repo_path = Path(self.config.workspace_dir) / "repos" / queued_task.repo_name.replace("/", "-")
            
            # Ensure repository is cloned
            await self._ensure_repository_cloned(queued_task.repo_name, repo_path)
            
            # Allocate container for this task
            allocated = await self.allocate_container(queued_task.repo_name, repo_path)
            
            if not allocated:
                logger.error("Failed to allocate container for task",
                            task_id=queued_task.task_id,
                            container=container_name)
                return
            
            try:
                # Execute the task
                result = await self.claude_dispatcher.execute_task(
                    container_name=container_name,
                    workspace_name=queued_task.workspace_name,
                    task_description=queued_task.task_description,
                    event=queued_task.event
                )
                
                logger.info("Task execution completed",
                           task_id=queued_task.task_id,
                           container=container_name,
                           success=result.success)
                
            finally:
                # Always release the container
                await self.release_container(container_name)
                
        except Exception as e:
            logger.error("Task processing failed",
                        task_id=queued_task.task_id,
                        container=container_name,
                        error=str(e))
    
    async def _ensure_repository_cloned(
        self,
        repo_name: str,
        repo_path: Path
    ) -> None:
        """Ensure repository is cloned to the workspace directory.
        
        Args:
            repo_name: Repository name (owner/repo)
            repo_path: Path where repository should be cloned
        """
        if repo_path.exists():
            # Repository already exists, pull latest changes
            try:
                cmd = ["git", "-C", str(repo_path), "pull", "origin", "main"]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                logger.info("Repository updated", repo=repo_name, path=str(repo_path))
                
            except Exception as e:
                logger.warning("Failed to update repository",
                              repo=repo_name,
                              error=str(e))
        else:
            # Clone the repository
            try:
                repo_path.parent.mkdir(parents=True, exist_ok=True)
                
                clone_url = f"https://github.com/{repo_name}.git"
                cmd = ["git", "clone", clone_url, str(repo_path)]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    logger.info("Repository cloned successfully",
                               repo=repo_name,
                               path=str(repo_path))
                else:
                    error_msg = stderr.decode('utf-8', errors='replace')
                    logger.error("Failed to clone repository",
                                repo=repo_name,
                                error=error_msg)
                    raise Exception(f"Git clone failed: {error_msg}")
                    
            except Exception as e:
                logger.error("Repository cloning failed",
                            repo=repo_name,
                            error=str(e))
                raise
    
    async def shutdown(self) -> None:
        """Shutdown the container pool and all workers."""
        logger.info("Shutting down container pool")
        
        # Cancel all worker tasks
        for container_name, worker_task in self.container_workers.items():
            worker_task.cancel()
            
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            logger.info("Worker shut down", container=container_name)
        
        # Clean up all containers
        for container_name in list(self.busy_containers.keys()):
            await self.release_container(container_name)
        
        logger.info("Container pool shutdown complete")
    
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
            webhook_config = WebhookConfig()
            webhook_config.workspaces_dir = self.config.workspace_dir
            workspace_manager = WorkspaceManager(project, webhook_config)
            
            # Create workspace for this container
            workspace_dir = workspace_manager.create_workspace(
                container_name, force=True  # Always recreate for fresh start
            )
            
            # Set up container manager
            container_manager = ContainerManager(project, webhook_config)
            
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
            
            webhook_config = WebhookConfig()
            webhook_config.workspaces_dir = self.config.workspace_dir
            workspace_manager = WorkspaceManager(project, webhook_config)
            
            container_manager = ContainerManager(project, webhook_config)
            
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