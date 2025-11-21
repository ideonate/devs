"""Container pool management for webhook tasks."""

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, Any, NamedTuple
from pathlib import Path
import structlog
import yaml

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager

from ..config import get_config
from .webhook_config import WebhookConfig
from ..github.models import WebhookEvent, DevsOptions, IssueEvent, PullRequestEvent, CommentEvent
from .claude_dispatcher import ClaudeDispatcher, TaskResult
from ..github.client import GitHubClient

logger = structlog.get_logger()


class QueuedTask(NamedTuple):
    """A task queued for execution in a container."""
    task_id: str
    repo_name: str
    task_description: str
    event: WebhookEvent
    task_type: str = 'claude'



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
        
        # Track single-queue repos and their assigned containers
        self.single_queue_repos: Dict[str, str] = {}  # repo_name -> container_name
        
        # Start worker tasks for each container
        self._start_workers()

        # Start the idle container cleanup task
        self.cleanup_worker = asyncio.create_task(self._idle_cleanup_worker())
        
        logger.info("Container pool initialized", 
                   containers=self.config.get_container_pool_list())
    
    
    def register_single_queue_repo(self, repo_name: str, container_name: str) -> None:
        """Register a repository as requiring single-queue processing.
        
        This is called by the worker after detecting single_queue in DEVS.yml.
        The registration is kept in memory only and resets on restart.
        
        Args:
            repo_name: Repository name (owner/repo)
            container_name: Container assigned to this repo
        """
        if repo_name not in self.single_queue_repos:
            self.single_queue_repos[repo_name] = container_name
            logger.info("Registered single-queue repository",
                       repo=repo_name,
                       container=container_name)
    
    def _read_devs_options(self, repo_path: Path, repo_name: str) -> DevsOptions:
        """Read and parse DEVS.yml options from repository.
        
        Args:
            repo_path: Path to repository
            repo_name: Repository name for logging
            
        Returns:
            DevsOptions with values from DEVS.yml or defaults
        """
        devs_options = DevsOptions()  # Start with defaults
        devs_yml_path = repo_path / "DEVS.yml"
        
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
                        if 'prompt_override' in data:
                            devs_options.prompt_override = data['prompt_override']
                        if 'direct_commit' in data:
                            devs_options.direct_commit = data['direct_commit']
                        if 'single_queue' in data:
                            devs_options.single_queue = data['single_queue']
                        
                        logger.info("Loaded DEVS.yml configuration",
                                   repo=repo_name,
                                   default_branch=devs_options.default_branch,
                                   has_prompt_extra=bool(devs_options.prompt_extra),
                                   has_prompt_override=bool(devs_options.prompt_override),
                                   direct_commit=devs_options.direct_commit,
                                   single_queue=devs_options.single_queue)
            except Exception as e:
                logger.warning("Failed to parse DEVS.yml",
                              repo=repo_name,
                              error=str(e))
                # Continue with defaults if parsing fails
        
        return devs_options
    
    async def queue_task(
        self,
        task_id: str,
        repo_name: str,
        task_description: str,
        event: WebhookEvent,
        task_type: str = 'claude'
    ) -> bool:
        """Queue a task for execution in the next available container.
        
        For repositories with single_queue enabled in DEVS.yml, all tasks
        are routed to the same container to avoid conflicts. The single_queue
        setting is detected after the first clone and cached in memory.
        
        Args:
            task_id: Unique task identifier
            repo_name: Repository name (owner/repo)
            task_description: Task description for Claude (unused for tests)
            event: Original webhook event
            task_type: Task type ('claude' or 'tests')
            
        Returns:
            True if task was queued successfully
        """
        try:
            # Check if we already know this repo needs single-queue processing
            # This is populated after the first clone by the worker
            single_queue_required = False
            
            if repo_name in self.single_queue_repos:
                # We already know this repo needs single-queue processing
                single_queue_required = True
                logger.info("Repository known to require single-queue processing",
                           repo=repo_name)
            
            # Determine which container to use
            best_container = None
            
            if single_queue_required:
                # Use the previously assigned container for this single-queue repo
                best_container = self.single_queue_repos[repo_name]
                logger.info("Using previously assigned container for single-queue repo",
                           repo=repo_name,
                           container=best_container)
            else:
                # Normal load balancing - find container with shortest queue
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
                task_type=task_type
            )
            
            # Add to queue
            await self.container_queues[best_container].put(queued_task)
            
            queue_size = self.container_queues[best_container].qsize()
            logger.info("Task queued successfully",
                       task_id=task_id,
                       container=best_container,
                       queue_size=queue_size,
                       repo=repo_name,
                       single_queue=single_queue_required)
            
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
            
            # After first clone, check if this repo needs single-queue processing
            # and register it in memory for future events
            if devs_options and devs_options.single_queue:
                if repo_name not in self.single_queue_repos:
                    # This is the first time we've seen this repo needs single-queue
                    # Register it with the current container
                    self.register_single_queue_repo(repo_name, dev_name)
                    logger.info("Detected single_queue requirement after first clone",
                               repo=repo_name,
                               container=dev_name)
            elif repo_name in self.single_queue_repos:
                # The repo was previously single-queue but no longer is
                # Remove it from the single_queue_repos tracking
                previous_container = self.single_queue_repos[repo_name]
                del self.single_queue_repos[repo_name]
                logger.info("Removed single_queue requirement - DEVS.yml no longer has single_queue=true",
                           repo=repo_name,
                           previously_assigned_container=previous_container)
            
            logger.info("Repository cloning completed, launching worker subprocess",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       devs_options_present=devs_options is not None)

            # Build JSON payload for stdin (no base64 encoding needed)
            stdin_payload = {
                "task_description": queued_task.task_description,
                "event": queued_task.event.model_dump(mode='json'),  # Use JSON mode for datetime serialization
            }
            if devs_options:
                stdin_payload["devs_options"] = devs_options.model_dump(mode='json')
            
            stdin_json = json.dumps(stdin_payload)
            
            # Build subprocess command (only basic args, large data via stdin)
            cmd = [
                sys.executable, "-m", "devs_webhook.cli.worker",
                "--task-id", queued_task.task_id,
                "--dev-name", dev_name,
                "--repo-name", repo_name,
                "--repo-path", str(repo_path),
                "--task-type", queued_task.task_type,
                "--timeout", str(3600)  # 60 minute timeout
            ]
            
            logger.info("Launching worker subprocess",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       command_length=len(' '.join(cmd)),
                       stdin_payload_size=len(stdin_json))

            # Launch subprocess with timeout
            # Set environment to suppress console output
            env = os.environ.copy()
            env['DEVS_WEBHOOK_MODE'] = '1'
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                # Wait for subprocess with timeout, sending JSON via stdin
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_json.encode('utf-8')),
                    timeout=3600  # 60 minute timeout
                )
                
                # Check result based on exit code
                if process.returncode == 0:
                    # Success - task completed
                    logger.info("Subprocess task completed successfully",
                               task_id=queued_task.task_id,
                               container=dev_name,
                               return_code=process.returncode)
                    
                    # Try to extract Claude's output from JSON if possible (for logging)
                    try:
                        result_data = json.loads(stdout.decode('utf-8'))
                        output_preview = result_data.get('output', '')[:200]
                        logger.info("Task output preview",
                                   task_id=queued_task.task_id,
                                   output_preview=output_preview)
                    except:
                        # If JSON parsing fails, just log that task succeeded
                        pass
                else:
                    # Failure - post error to GitHub
                    stdout_content = stdout.decode('utf-8', errors='replace') if stdout else ''
                    stderr_content = stderr.decode('utf-8', errors='replace') if stderr else ''
                    
                    # Try to extract error from JSON if possible
                    error_msg = f"Task failed with exit code {process.returncode}"
                    try:
                        error_data = json.loads(stdout_content)
                        if error_data.get('error'):
                            error_msg = error_data['error']
                    except:
                        pass
                    
                    logger.error("Subprocess task failed",
                                task_id=queued_task.task_id,
                                container=dev_name,
                                return_code=process.returncode,
                                error=error_msg)
                    
                    # Post error to GitHub with both stdout and stderr
                    error_details = f"Task processing failed with exit code {process.returncode}\n\n"
                    if error_msg != f"Task failed with exit code {process.returncode}":
                        error_details += f"Error: {error_msg}\n\n"
                    if stderr_content:
                        error_details += f"Stderr output:\n```\n{stderr_content[:1500]}\n```\n\n"
                    if stdout_content and not stdout_content.startswith('{'):
                        # Include stdout if it's not JSON
                        error_details += f"Stdout output:\n```\n{stdout_content[:1500]}\n```"
                    
                    await self._post_subprocess_error_to_github(
                        queued_task,
                        error_details
                    )
                    
            except asyncio.TimeoutError:
                logger.error("Subprocess task timed out",
                            task_id=queued_task.task_id,
                            container=dev_name,
                            timeout_seconds=3600)

                # Kill the subprocess
                process.kill()
                await process.wait()
                
                # Post timeout error to GitHub
                await self._post_subprocess_error_to_github(
                    queued_task,
                    "Task processing timed out after 60 minutes. The task may have been too complex or encountered an issue."
                )
                
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
            
            # Post error to GitHub for any other exceptions
            await self._post_subprocess_error_to_github(
                queued_task,
                f"Task processing encountered an error: {type(e).__name__}\n\n{str(e)}"
            )
            
            # Task execution failed, but we've logged it - don't re-raise
    
    async def _ensure_repository_cloned(
        self,
        repo_name: str,
        repo_path: Path
    ) -> DevsOptions:
        """Ensure repository is cloned to the workspace directory.
        
        Uses a simple strategy: if repository exists but pull fails,
        remove it and do a fresh clone.
        
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
            # Repository already exists, try to pull latest changes
            try:
                logger.info("Repository exists, attempting to pull latest changes",
                           repo=repo_name,
                           repo_path=str(repo_path))
                
                # Set up authentication for private repos
                if self.config.github_token:
                    # Configure the token for this specific repo
                    remote_url = f"https://{self.config.github_token}@github.com/{repo_name}.git"
                    set_remote_cmd = ["git", "-C", str(repo_path), "remote", "set-url", "origin", remote_url]
                    await asyncio.create_subprocess_exec(*set_remote_cmd)
                
                # Try to pull - using main as default, but this might fail
                cmd = ["git", "-C", str(repo_path), "pull"]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    logger.info("Git pull succeeded",
                               repo=repo_name,
                               stdout=stdout.decode()[:200] if stdout else "")
                    logger.info("Repository updated", repo=repo_name, path=str(repo_path))
                else:
                    # Pull failed - remove and re-clone
                    logger.warning("Git pull failed, removing and re-cloning",
                                  repo=repo_name,
                                  return_code=process.returncode,
                                  stderr=stderr.decode()[:200] if stderr else "")
                    
                    # Remove the existing directory
                    logger.info("Removing existing repository directory",
                               repo=repo_name,
                               repo_path=str(repo_path))
                    shutil.rmtree(repo_path)
                    
                    # Now fall through to clone logic
                    
            except Exception as e:
                logger.warning("Failed to update repository, removing and re-cloning",
                              repo=repo_name,
                              error=str(e),
                              error_type=type(e).__name__)
                
                # Remove the existing directory
                try:
                    shutil.rmtree(repo_path)
                    logger.info("Removed existing repository directory",
                               repo=repo_name,
                               repo_path=str(repo_path))
                except Exception as rm_error:
                    logger.error("Failed to remove repository directory",
                                repo=repo_name,
                                repo_path=str(repo_path),
                                error=str(rm_error))
                    raise
        
        # If we get here, either the repo didn't exist or we removed it
        if not repo_path.exists():
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
        
        # Read DEVS.yml configuration using shared method
        devs_options = self._read_devs_options(repo_path, repo_name)
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
    
    async def _post_subprocess_error_to_github(self, queued_task: QueuedTask, error_message: str) -> None:
        """Post an error message to GitHub when subprocess fails.
        
        Args:
            queued_task: The task that failed
            error_message: Error message to post
        """
        try:
            # Skip GitHub operations for test events
            if queued_task.event.is_test:
                logger.info("Skipping GitHub error comment for test event", 
                           error=error_message[:200])
                return
            
            # Create GitHub client
            github_client = GitHubClient(self.config.github_token)
            
            # Build error comment
            comment = f"""I encountered an error while processing your request:

{error_message}

Please check the webhook handler logs for more details, or try mentioning me again."""
            
            # Post comment based on event type
            repo_name = queued_task.event.repository.full_name
            
            if isinstance(queued_task.event, IssueEvent):
                await github_client.comment_on_issue(
                    repo_name, queued_task.event.issue.number, comment
                )
            elif isinstance(queued_task.event, PullRequestEvent):
                await github_client.comment_on_pr(
                    repo_name, queued_task.event.pull_request.number, comment
                )
            elif isinstance(queued_task.event, CommentEvent):
                if queued_task.event.issue:
                    await github_client.comment_on_issue(
                        repo_name, queued_task.event.issue.number, comment
                    )
                elif queued_task.event.pull_request:
                    await github_client.comment_on_pr(
                        repo_name, queued_task.event.pull_request.number, comment
                    )
            
            logger.info("Posted error comment to GitHub",
                       task_id=queued_task.task_id,
                       repo=repo_name)
                       
        except Exception as e:
            logger.error("Failed to post error to GitHub",
                        task_id=queued_task.task_id,
                        error=str(e))
    
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
                "single_queue_repos": self.single_queue_repos.copy(),
            }

    async def _idle_cleanup_worker(self) -> None:
        """Periodically clean up idle containers."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                async with self._lock:
                    now = datetime.now(tz=timezone.utc)
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