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



class ContainerPool:
    """Manages a pool of named containers for webhook tasks."""
    
    def __init__(self):
        """Initialize container pool."""
        self.config = get_config()
        self.claude_dispatcher = ClaudeDispatcher()

        # Track running containers for idle cleanup
        self.running_containers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        
        # Task queues - one per dev name
        self.container_queues: Dict[str, asyncio.Queue] = {
            dev_name: asyncio.Queue() for dev_name in self.config.container_pool
        }
        
        # Container workers - one per dev name
        self.container_workers: Dict[str, asyncio.Task] = {}
        
        # Start worker tasks for each container
        self._start_workers()

        # Start the idle container cleanup task
        self.cleanup_worker = asyncio.create_task(self._idle_cleanup_worker())
        
        logger.info("Container pool initialized", 
                   containers=self.config.container_pool)
    
    
    
    async def queue_task(
        self,
        task_id: str,
        repo_name: str,
        task_description: str,
        event: WebhookEvent,
    ) -> bool:
        """Queue a task for execution in the next available container.
        
        Args:
            task_id: Unique task identifier
            repo_name: Repository name (owner/repo)
            task_description: Task description for Claude
            event: Original webhook event
            
        Returns:
            True if task was queued successfully
        """
        try:
            # Find container with shortest queue
            best_container = None
            min_queue_size = float('inf')
            
            for dev_name in self.config.container_pool:
                queue_size = self.container_queues[dev_name].qsize()
                if queue_size < min_queue_size:
                    min_queue_size = queue_size
                    best_container = dev_name
            
            if best_container is None:
                logger.error("No containers available for task queuing")
                return False
            
            # Create queued task
            queued_task = QueuedTask(
                task_id=task_id,
                repo_name=repo_name,
                task_description=task_description,
                event=event,
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
        for dev_name in self.config.container_pool:
            worker_task = asyncio.create_task(
                self._container_worker(dev_name)
            )
            self.container_workers[dev_name] = worker_task
            
            logger.info("Started worker for container", container=dev_name)
    
    async def _container_worker(self, dev_name: str) -> None:
        """Worker process for a specific container.
        
        Args:
            dev_name: Name of the container this worker manages
        """
        logger.info("Container worker started", container=dev_name)
        
        try:
            while True:
                # Wait for a task from the queue
                try:
                    queued_task = await self.container_queues[dev_name].get()
                    
                    logger.info("Worker processing task",
                               container=dev_name,
                               task_id=queued_task.task_id,
                               repo=queued_task.repo_name)
                    
                    # Process the task
                    await self._process_task(dev_name, queued_task)
                    
                    # Mark task as done
                    self.container_queues[dev_name].task_done()
                    
                except asyncio.CancelledError:
                    logger.info("Container worker cancelled", container=dev_name)
                    break
                except Exception as e:
                    logger.error("Error in container worker",
                                container=dev_name,
                                error=str(e))
                    # Continue processing other tasks
                    continue
                    
        except Exception as e:
            logger.error("Container worker failed",
                        container=dev_name,
                        error=str(e))
    
    async def _process_task(self, dev_name: str, queued_task: QueuedTask) -> None:
        """Process a single task in a container.
        
        Args:
            dev_name: Name of container to execute in
            queued_task: Task to process
        """
        repo_name = queued_task.repo_name
        repo_path = self.config.repo_cache_dir / repo_name.replace("/", "-")
        
        # The workspace name is determined by the project and the dev_name
        project = Project(repo_path)
        workspace_name = f"{project.info.name}-{dev_name}"

        try:
            # Ensure repository is cloned
            await self._ensure_repository_cloned(repo_name, repo_path)

            # Set up container for this repository
            setup_success = await self._setup_container(
                dev_name, repo_name, repo_path
            )

            if not setup_success:
                logger.error("Failed to set up container for task",
                             task_id=queued_task.task_id,
                             container=dev_name)
                return

            # Mark container as active
            async with self._lock:
                self.running_containers[dev_name] = {
                    "repo_path": repo_path,
                    "last_used": datetime.now(),
                }

            # Execute the task
            result = await self.claude_dispatcher.execute_task(
                dev_name=dev_name,
                workspace_name=workspace_name,
                task_description=queued_task.task_description,
                event=queued_task.event
            )
            
            logger.info("Task execution completed",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       success=result.success)
                
        except Exception as e:
            logger.error("Task processing failed",
                        task_id=queued_task.task_id,
                        container=dev_name,
                        error=str(e))
            
            # If setup failed, we might have a mess. Clean up.
            await self._cleanup_container(dev_name, repo_path)
    
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
        
        # Cancel the cleanup worker
        self.cleanup_worker.cancel()
        try:
            await self.cleanup_worker
        except asyncio.CancelledError:
            pass

        # Cancel all worker tasks
        for dev_name, worker_task in self.container_workers.items():
            worker_task.cancel()
            
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            logger.info("Worker shut down", container=dev_name)
        
        # Clean up any remaining running containers
        async with self._lock:
            for dev_name, info in self.running_containers.items():
                await self._cleanup_container(dev_name, info["repo_path"])

        logger.info("Container pool shutdown complete")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current pool status."""
        async with self._lock:
            return {
                "container_queues": {
                    name: queue.qsize()
                    for name, queue in self.container_queues.items()
                },
                "running_containers": {
                    name: {
                        "repo_path": str(info["repo_path"]),
                        "last_used": info["last_used"].isoformat(),
                    }
                    for name, info in self.running_containers.items()
                },
                "total_containers": len(self.config.container_pool),
            }

    async def _idle_cleanup_worker(self) -> None:
        """Periodically clean up idle containers."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                async with self._lock:
                    now = datetime.now()
                    idle_timeout = timedelta(minutes=self.config.container_timeout_minutes)
                    
                    idle_containers = []
                    for dev_name, info in self.running_containers.items():
                        if now - info["last_used"] > idle_timeout:
                            idle_containers.append((dev_name, info["repo_path"]))
                    
                    for dev_name, repo_path in idle_containers:
                        logger.info("Container idle, cleaning up", container=dev_name)
                        await self._cleanup_container(dev_name, repo_path)
                        del self.running_containers[dev_name]

            except asyncio.CancelledError:
                logger.info("Idle cleanup worker cancelled")
                break
            except Exception as e:
                logger.error("Error in idle cleanup worker", error=str(e))
    
    async def _setup_container(
        self, 
        dev_name: str, 
        repo_name: str, 
        repo_path: Path
    ) -> bool:
        """Set up a container for a repository.
        
        Args:
            dev_name: Name of container to set up
            repo_name: Repository name
            repo_path: Path to repository
            
        Returns:
            True if setup successful
        """
        try:
            # Create a temporary project for this repo
            project = Project(repo_path)
            
            # Set up shared configuration for CLI interoperability
            webhook_config = WebhookConfig()
            workspace_manager = WorkspaceManager(project, webhook_config)
            
            # Create workspace for this container
            # Note: dev_name is the pool name (eamonn/harry/darren)
            # ContainerManager will generate proper Docker container name: dev-org-repo-poolname
            workspace_dir = workspace_manager.create_workspace(
                dev_name, force=True
            )
            
            # Set up container manager
            container_manager = ContainerManager(project, webhook_config)
            
            # Ensure container is running using proper container name
            success = container_manager.ensure_container_running(
                dev_name, workspace_dir, force_rebuild=False
            )
            
            if success:
                logger.info("Container setup complete",
                           container=dev_name,
                           repo=repo_name,
                           workspace=str(workspace_dir))
            
            return success
            
        except Exception as e:
            logger.error("Container setup failed",
                        container=dev_name,
                        repo=repo_name,
                        error=str(e))
            return False
    
    async def _cleanup_container(self, dev_name: str, repo_path: Path) -> None:
        """Clean up a container after use.
        
        Args:
            dev_name: Name of container to clean up
            repo_path: Path to repository on host
        """
        try:
            # Create project and managers for cleanup
            project = Project(repo_path)
            
            webhook_config = WebhookConfig()
            workspace_manager = WorkspaceManager(project, webhook_config)
            
            container_manager = ContainerManager(project, webhook_config)
            
            # Stop container
            container_manager.stop_container(dev_name)
            
            # Remove workspace
            workspace_manager.remove_workspace(dev_name)
            
            logger.info("Container cleanup complete", container=dev_name)
            
        except Exception as e:
            logger.error("Container cleanup failed",
                        container=dev_name,
                        error=str(e))