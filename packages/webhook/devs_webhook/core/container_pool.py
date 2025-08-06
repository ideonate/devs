"""Container pool management for webhook tasks."""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Any, NamedTuple
from pathlib import Path
import structlog
import yaml

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager

from ..config import get_config
from .webhook_config import WebhookConfig
from ..github.models import WebhookEvent, DevsOptions
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
            dev_name: asyncio.Queue() for dev_name in self.config.get_container_pool_list()
        }
        
        # Container workers - one per dev name
        self.container_workers: Dict[str, asyncio.Task] = {}
        
        # Start worker tasks for each container
        self._start_workers()

        # Start the idle container cleanup task
        self.cleanup_worker = asyncio.create_task(self._idle_cleanup_worker())
        
        logger.info("Container pool initialized", 
                   containers=self.config.get_container_pool_list())
    
    
    
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
            
            for dev_name in self.config.get_container_pool_list():
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
        for dev_name in self.config.get_container_pool_list():
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
                    
                    try:
                        logger.info("Worker processing task",
                                   container=dev_name,
                                   task_id=queued_task.task_id,
                                   repo=queued_task.repo_name)
                        
                        # Process the task via subprocess for Docker safety
                        await self._process_task_subprocess(dev_name, queued_task)
                        
                    finally:
                        # Always mark task as done, regardless of success/failure
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
        
        logger.info("Starting task processing",
                   task_id=queued_task.task_id,
                   container=dev_name,
                   repo_name=repo_name,
                   repo_path=str(repo_path))

        try:
            # Ensure repository is cloned FIRST, before creating Project instance
            logger.info("Ensuring repository is cloned",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       repo_name=repo_name)
            
            devs_options = await self._ensure_repository_cloned(repo_name, repo_path)
            
            logger.info("Repository cloning completed",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       devs_options_present=devs_options is not None)

            # NOW create the project instance after the repository exists
            logger.info("Creating project instance",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       repo_path=str(repo_path))
            
            project = Project(repo_path)
            workspace_name = project.get_workspace_name(dev_name)
            
            logger.info("Project created successfully",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       project_name=project.info.name,
                       workspace_name=workspace_name)

            logger.info("Container and workspace setup will be handled by exec_claude (like CLI)",
                       task_id=queued_task.task_id,
                       container=dev_name)

            # Mark container as active
            logger.info("Marking container as active",
                       task_id=queued_task.task_id,
                       container=dev_name)
            
            async with self._lock:
                self.running_containers[dev_name] = {
                    "repo_path": repo_path,
                    "last_used": datetime.now(),
                }

            # Execute the task
            logger.info("Executing task with Claude dispatcher",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       workspace_name=workspace_name)
            
            result = await self.claude_dispatcher.execute_task(
                dev_name=dev_name,
                repo_path=repo_path,
                task_description=queued_task.task_description,
                event=queued_task.event,
                devs_options=devs_options
            )
            
            if result.success:
                logger.info("Task execution completed successfully",
                           task_id=queued_task.task_id,
                           container=dev_name,
                           output_length=len(result.output) if result.output else 0)
            else:
                logger.error("Task execution failed",
                            task_id=queued_task.task_id,
                            container=dev_name,
                            error=result.error)
                
        except Exception as e:
            logger.error("Task processing failed",
                        task_id=queued_task.task_id,
                        container=dev_name,
                        repo_name=repo_name,
                        repo_path=str(repo_path),
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True)
            
            # Task execution failed, but no cleanup needed since setup is deferred to exec_claude
    
    async def _process_task_subprocess(self, dev_name: str, queued_task: QueuedTask) -> None:
        """Process a single task via subprocess for Docker safety.
        
        Args:
            dev_name: Name of container to execute in
            queued_task: Task to process
        """
        repo_name = queued_task.repo_name
        repo_path = self.config.repo_cache_dir / repo_name.replace("/", "-")
        
        logger.info("Starting task processing via subprocess",
                   task_id=queued_task.task_id,
                   container=dev_name,
                   repo_name=repo_name,
                   repo_path=str(repo_path))

        try:
            # Ensure repository is cloned FIRST, before launching subprocess
            logger.info("Ensuring repository is cloned",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       repo_name=repo_name)
            
            devs_options = await self._ensure_repository_cloned(repo_name, repo_path)
            
            logger.info("Repository cloning completed, launching worker subprocess",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       devs_options_present=devs_options is not None)

            # Build JSON payload for stdin (no base64 encoding needed)
            stdin_payload = {
                "task_description": queued_task.task_description,
                "event": queued_task.event.model_dump(),
            }
            if devs_options:
                stdin_payload["devs_options"] = devs_options.model_dump()
            
            stdin_json = json.dumps(stdin_payload)
            
            # Build subprocess command (only basic args, large data via stdin)
            cmd = [
                sys.executable, "-m", "devs_webhook.cli.worker",
                "--task-id", queued_task.task_id,
                "--dev-name", dev_name,
                "--repo-name", repo_name,
                "--repo-path", str(repo_path),
                "--timeout", str(1800)  # 30 minute timeout
            ]
            
            logger.info("Launching worker subprocess",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       command_length=len(' '.join(cmd)),
                       stdin_payload_size=len(stdin_json))

            # Launch subprocess with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # Wait for subprocess with timeout, sending JSON via stdin
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_json.encode('utf-8')),
                    timeout=1800  # 30 minute timeout
                )
                
                # Parse result
                if process.returncode == 0:
                    # Success - parse JSON output
                    try:
                        result_data = json.loads(stdout.decode('utf-8'))
                        logger.info("Subprocess task completed successfully",
                                   task_id=queued_task.task_id,
                                   container=dev_name,
                                   output_length=len(result_data.get('output', '')))
                    except json.JSONDecodeError as e:
                        logger.error("Failed to parse subprocess JSON output",
                                    task_id=queued_task.task_id,
                                    container=dev_name,
                                    stdout=stdout.decode('utf-8')[:500],
                                    json_error=str(e))
                        raise Exception(f"Subprocess JSON parsing failed: {e}")
                else:
                    # Failure - log error details
                    try:
                        error_data = json.loads(stdout.decode('utf-8'))
                        error_msg = error_data.get('error', 'Unknown subprocess error')
                    except json.JSONDecodeError:
                        error_msg = f"Subprocess failed with return code {process.returncode}"
                    
                    logger.error("Subprocess task failed",
                                task_id=queued_task.task_id,
                                container=dev_name,
                                return_code=process.returncode,
                                error=error_msg,
                                stderr=stderr.decode('utf-8')[:500] if stderr else '')
                    
                    # Don't raise exception here - just log the failure
                    # The task is considered processed even if it failed
                    
            except asyncio.TimeoutError:
                logger.error("Subprocess task timed out",
                            task_id=queued_task.task_id,
                            container=dev_name,
                            timeout_seconds=1800)
                
                # Kill the subprocess
                process.kill()
                await process.wait()
                
                # Don't raise exception - just log the timeout
                
        except Exception as e:
            logger.error("Subprocess task processing failed",
                        task_id=queued_task.task_id,
                        container=dev_name,
                        repo_name=repo_name,
                        repo_path=str(repo_path),
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True)
            
            # Task execution failed, but we've logged it - don't re-raise
    
    async def _ensure_repository_cloned(
        self,
        repo_name: str,
        repo_path: Path
    ) -> DevsOptions:
        """Ensure repository is cloned to the workspace directory.
        
        Args:
            repo_name: Repository name (owner/repo)
            repo_path: Path where repository should be cloned
            
        Returns:
            DevsOptions parsed from DEVS.yml or defaults
        """
        logger.info("Checking repository status",
                   repo=repo_name,
                   repo_path=str(repo_path),
                   exists=repo_path.exists())
        
        if repo_path.exists():
            # Repository already exists, pull latest changes
            try:
                logger.info("Repository exists, pulling latest changes",
                           repo=repo_name,
                           repo_path=str(repo_path))
                
                # Set up authentication for private repos
                if self.config.github_token:
                    # Configure the token for this specific repo
                    remote_url = f"https://{self.config.github_token}@github.com/{repo_name}.git"
                    set_remote_cmd = ["git", "-C", str(repo_path), "remote", "set-url", "origin", remote_url]
                    await asyncio.create_subprocess_exec(*set_remote_cmd)
                
                cmd = ["git", "-C", str(repo_path), "pull", "origin", "main"]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                logger.info("Git pull completed",
                           repo=repo_name,
                           return_code=process.returncode,
                           stdout=stdout.decode()[:200] if stdout else "",
                           stderr=stderr.decode()[:200] if stderr else "")
                
                logger.info("Repository updated", repo=repo_name, path=str(repo_path))
                
            except Exception as e:
                logger.warning("Failed to update repository",
                              repo=repo_name,
                              error=str(e),
                              error_type=type(e).__name__)
        else:
            # Clone the repository
            try:
                logger.info("Repository does not exist, cloning",
                           repo=repo_name,
                           repo_path=str(repo_path))
                
                repo_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Use GitHub token for authentication
                if self.config.github_token:
                    clone_url = f"https://{self.config.github_token}@github.com/{repo_name}.git"
                else:
                    clone_url = f"https://github.com/{repo_name}.git"
                
                cmd = ["git", "clone", clone_url, str(repo_path)]
                
                # Don't log the token!
                safe_url = f"https://github.com/{repo_name}.git"
                logger.info("Starting git clone",
                           repo=repo_name,
                           clone_url=safe_url,
                           target_path=str(repo_path))
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                logger.info("Git clone completed",
                           repo=repo_name,
                           return_code=process.returncode,
                           stdout=stdout.decode()[:200] if stdout else "",
                           stderr=stderr.decode()[:200] if stderr else "")
                
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
        
        # Check for DEVS.yml file
        devs_yml_path = repo_path / "DEVS.yml"
        devs_options = DevsOptions()  # Start with defaults
        
        if devs_yml_path.exists():
            try:
                with open(devs_yml_path, 'r') as f:
                    data = yaml.safe_load(f)
                    if data:
                        # Update devs_options with values from DEVS.yml
                        if 'default_branch' in data:
                            devs_options.default_branch = data['default_branch']
                        if 'prompt_extra' in data:
                            devs_options.prompt_extra = data['prompt_extra']
                        
                        logger.info("Loaded DEVS.yml configuration",
                                   repo=repo_name,
                                   default_branch=devs_options.default_branch,
                                   has_prompt_extra=bool(devs_options.prompt_extra))
            except Exception as e:
                logger.warning("Failed to parse DEVS.yml",
                              repo=repo_name,
                              error=str(e))
                # Continue with defaults if parsing fails
        
        return devs_options
    
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
                "total_containers": len(self.config.get_container_pool_list()),
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
    
    
    async def _cleanup_container(self, dev_name: str, repo_path: Path) -> None:
        """Clean up a container after use.
        
        Args:
            dev_name: Name of container to clean up
            repo_path: Path to repository on host
        """
        try:
            # Create project and managers for cleanup
            project = Project(repo_path)
            
            # Use the same config as the rest of the webhook handler
            workspace_manager = WorkspaceManager(project, self.config)
            container_manager = ContainerManager(project, self.config)
            
            # Stop container
            logger.info("Starting container stop", container=dev_name)
            stop_success = container_manager.stop_container(dev_name)
            logger.info("Container stop result", container=dev_name, success=stop_success)
            
            # Remove workspace
            logger.info("Starting workspace removal", container=dev_name)
            workspace_success = workspace_manager.remove_workspace(dev_name)
            logger.info("Workspace removal result", container=dev_name, success=workspace_success)
            
            logger.info("Container cleanup complete", 
                       container=dev_name,
                       container_stopped=stop_success,
                       workspace_removed=workspace_success)
            
        except Exception as e:
            logger.error("Container cleanup failed",
                        container=dev_name,
                        error=str(e))