"""Container pool management for webhook tasks."""

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, NamedTuple
from pathlib import Path
import structlog

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from devs_common.devs_config import DevsConfigLoader, DevsOptions
from devs_common.utils.config_hash import compute_env_config_hash

from ..config import get_config
from ..github.models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent
from .base_dispatcher import TaskResult
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

    def __init__(self, enable_cleanup_worker: bool = True):
        """Initialize container pool.

        Args:
            enable_cleanup_worker: If True (default), starts background task to
                clean up idle/old containers. Set to False for burst mode where
                cleanup should be done manually after processing completes.
        """
        self.config = get_config()

        # Track running containers for idle cleanup
        self.running_containers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        # Task queues - one per dev name
        self.container_queues: Dict[str, asyncio.Queue] = {
            dev_name: asyncio.Queue() for dev_name in self.config.get_container_pool_list()
        }

        # Container workers - one per dev name
        self.container_workers: Dict[str, asyncio.Task] = {}

        # Cache DEVS.yml configuration for repositories
        # Stores tuple of (DevsOptions, config_hash) for invalidation
        self.repo_configs: Dict[str, tuple[DevsOptions, str]] = {}  # repo_name -> (DevsOptions, hash)

        # Track which container is assigned to single-queue repos
        self.single_queue_assignments: Dict[str, str] = {}  # repo_name -> container_name

        # Start worker tasks for each container
        self._start_workers()

        # Start the idle container cleanup task (optional - disabled for burst mode)
        self._cleanup_worker_enabled = enable_cleanup_worker
        if enable_cleanup_worker:
            self.cleanup_worker = asyncio.create_task(self._idle_cleanup_worker())
            logger.info("Container pool initialized with cleanup worker",
                       containers=self.config.get_container_pool_list())
        else:
            self.cleanup_worker = None
            logger.info("Container pool initialized (cleanup worker disabled)",
                       containers=self.config.get_container_pool_list())
    
    
    def get_repo_config(self, repo_name: str) -> Optional[DevsOptions]:
        """Get cached repository configuration, checking for config changes.

        Computes current config hash and compares with cached hash.
        If hash differs, invalidates cache and returns None to trigger reload.

        Args:
            repo_name: Repository name (owner/repo)

        Returns:
            DevsOptions if cached and still valid, None if not cached or stale
        """
        cached = self.repo_configs.get(repo_name)
        if cached is None:
            return None

        devs_options, cached_hash = cached

        # Check if config files have changed
        project_name = repo_name.replace('/', '-')
        current_hash = compute_env_config_hash(project_name)

        if current_hash != cached_hash:
            logger.info("Config hash changed, invalidating cache",
                       repo=repo_name,
                       old_hash=cached_hash[:8] + "...",
                       new_hash=current_hash[:8] + "...")
            del self.repo_configs[repo_name]
            return None

        return devs_options
    
    async def ensure_repo_config(self, repo_name: str) -> DevsOptions:
        """Ensure repository configuration is loaded and cached.
        
        First checks user-specific DEVS.yml files, only clones repository if needed.
        
        Args:
            repo_name: Repository name (owner/repo)
            
        Returns:
            DevsOptions from cache or newly loaded from DEVS.yml
        """
        # Check if already cached (and still valid)
        cached = self.get_repo_config(repo_name)
        if cached is not None:
            return cached

        # Try to load from user-specific configuration first (no cloning needed)
        devs_options = self._try_load_user_config(repo_name)
        
        if devs_options is not None:
            # Found user configuration, cache it with hash
            project_name = repo_name.replace('/', '-')
            config_hash = compute_env_config_hash(project_name)
            logger.info("Repository config loaded from user-specific DEVS.yml (no cloning needed)",
                       repo=repo_name,
                       config_hash=config_hash[:8] + "...")
            self.repo_configs[repo_name] = (devs_options, config_hash)
        else:
            # No user config found, need to clone and read repository DEVS.yml
            logger.info("No user-specific config found, cloning repository to read DEVS.yml",
                       repo=repo_name)
            
            # Calculate repo path
            repo_path = self.config.repo_cache_dir / repo_name.replace('/', '-')
            
            # Clone repository and read config
            devs_options = await self._ensure_repository_cloned(repo_name, repo_path)

            # Cache the config with hash
            project_name = repo_name.replace('/', '-')
            config_hash = compute_env_config_hash(project_name)
            self.repo_configs[repo_name] = (devs_options, config_hash)
        
        # Update single-queue assignment tracking if needed
        if devs_options.single_queue and repo_name not in self.single_queue_assignments:
            # We'll assign a container when the first task is actually queued
            pass
        
        logger.info("Repository config cached",
                   repo=repo_name,
                   single_queue=devs_options.single_queue,
                   ci_enabled=devs_options.ci_enabled)
        
        return devs_options
    
    def _try_load_user_config(self, repo_name: str) -> Optional[DevsOptions]:
        """Try to load configuration from user-specific DEVS.yml files only.
        
        Checks for user-specific configuration without cloning the repository.
        
        Args:
            repo_name: Repository name (owner/repo)
            
        Returns:
            DevsOptions if user-specific config exists, None otherwise
        """
        # Check for user-specific configuration files
        user_envs_dir = Path.home() / ".devs" / "envs"
        default_devs_yml = user_envs_dir / "default" / "DEVS.yml"
        project_name = repo_name.replace('/', '-')  # Convert org/repo to org-repo
        project_devs_yml = user_envs_dir / project_name / "DEVS.yml"
        
        # If no user configuration files exist, return None
        if not default_devs_yml.exists() and not project_devs_yml.exists():
            return None
        
        # Load configuration without repository files (user configs only)
        # Create a fake path that doesn't exist to skip repository DEVS.yml
        fake_repo_path = Path("/dev/null/fake_repo_path")
        devs_options = DevsConfigLoader.load(project_name=project_name, repo_path=fake_repo_path)
        
        logger.info("Loaded user-specific DEVS.yml configuration",
                   repo=repo_name,
                   default_file_exists=default_devs_yml.exists(),
                   project_file_exists=project_devs_yml.exists(),
                   default_branch=devs_options.default_branch,
                   single_queue=devs_options.single_queue,
                   ci_enabled=devs_options.ci_enabled,
                   env_vars_containers=list(devs_options.env_vars.keys()) if devs_options.env_vars else [])
        
        return devs_options
    
    def _read_devs_options(self, repo_path: Path, repo_name: str) -> DevsOptions:
        """Read and parse DEVS.yml options from multiple sources.
        
        Uses the shared DevsConfigLoader to load from:
        1. ~/.devs/envs/{org-repo}/DEVS.yml (user-specific overrides)
        2. ~/.devs/envs/default/DEVS.yml (user defaults)  
        3. {repo_path}/DEVS.yml (repository configuration)
        
        Args:
            repo_path: Path to repository
            repo_name: Repository name (org/repo format)
            
        Returns:
            DevsOptions with values from DEVS.yml files or defaults
        """
        project_name = repo_name.replace('/', '-')  # Convert org/repo to org-repo
        devs_options = DevsConfigLoader.load(project_name=project_name, repo_path=repo_path)
        
        # Check which files exist for logging
        user_envs_dir = Path.home() / ".devs" / "envs"
        repo_devs_yml = repo_path / "DEVS.yml"
        default_devs_yml = user_envs_dir / "default" / "DEVS.yml"
        project_devs_yml = user_envs_dir / project_name / "DEVS.yml"
        
        logger.info("Loaded DEVS.yml configuration from multiple sources",
                   repo=repo_name,
                   repo_file_exists=repo_devs_yml.exists(),
                   default_file_exists=default_devs_yml.exists(),
                   project_file_exists=project_devs_yml.exists(),
                   default_branch=devs_options.default_branch,
                   has_prompt_extra=bool(devs_options.prompt_extra),
                   has_prompt_override=bool(devs_options.prompt_override),
                   direct_commit=devs_options.direct_commit,
                   single_queue=devs_options.single_queue,
                   ci_enabled=devs_options.ci_enabled,
                   ci_test_command=devs_options.ci_test_command,
                   ci_branches=devs_options.ci_branches,
                   env_vars_containers=list(devs_options.env_vars.keys()) if devs_options.env_vars else [])
        
        return devs_options
    
    async def _ensure_repository_files_available(self, repo_name: str, repo_path: Path) -> None:
        """Ensure repository files are available locally without re-reading config.
        
        This is used when we already have the DEVS.yml config cached but need
        to ensure the actual repository files are available for the worker.
        
        Args:
            repo_name: Repository name (owner/repo)
            repo_path: Path where repository should be cloned
        """
        logger.info("Ensuring repository files are available",
                   repo=repo_name,
                   repo_path=str(repo_path),
                   exists=repo_path.exists())
        
        if repo_path.exists():
            # Repository already exists, try to pull latest changes
            try:
                logger.info("Repository exists, fetching latest changes",
                           repo=repo_name,
                           repo_path=str(repo_path))
                
                # Set up authentication for private repos
                if self.config.github_token:
                    set_remote_cmd = ["git", "-C", str(repo_path), "remote", "set-url", "origin",
                                    f"https://x-access-token:{self.config.github_token}@github.com/{repo_name}.git"]
                    
                    process = await asyncio.create_subprocess_exec(*set_remote_cmd)
                    await process.wait()
                
                # Fetch all branches to ensure we have all commits
                fetch_cmd = ["git", "-C", str(repo_path), "fetch", "--all"]
                process = await asyncio.create_subprocess_exec(
                    *fetch_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode('utf-8', errors='replace') if stderr else "Unknown error"
                    logger.warning("Failed to fetch repository, will try fresh clone",
                                  repo=repo_name,
                                  error=error_msg)

                    # Remove the directory and fall through to fresh clone
                    import shutil
                    shutil.rmtree(repo_path)
                else:
                    logger.info("Repository fetch successful",
                               repo=repo_name)

                    # Checkout the default branch to ensure devcontainer files are from the right branch
                    await self._checkout_default_branch(repo_name, repo_path)

                    return  # Success, repository is up to date
                    
            except Exception as e:
                logger.warning("Error during repository pull, will try fresh clone",
                              repo=repo_name,
                              error=str(e))
                # Remove the directory and fall through to fresh clone
                import shutil
                if repo_path.exists():
                    shutil.rmtree(repo_path)
        
        # Clone repository fresh (either first time or after failed pull)
        try:
            logger.info("Cloning repository",
                       repo=repo_name,
                       repo_path=str(repo_path))
            
            # Ensure parent directory exists
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Clone with authentication if we have a token
            if self.config.github_token:
                clone_url = f"https://x-access-token:{self.config.github_token}@github.com/{repo_name}.git"
            else:
                clone_url = f"https://github.com/{repo_name}.git"
            
            clone_cmd = ["git", "clone", clone_url, str(repo_path)]
            process = await asyncio.create_subprocess_exec(
                *clone_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Repository cloned successfully",
                           repo=repo_name)

                # Checkout the default branch to ensure devcontainer files are from the right branch
                await self._checkout_default_branch(repo_name, repo_path)
            else:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else stdout.decode('utf-8', errors='replace')
                logger.error("Git clone failed",
                            repo=repo_name,
                            error=error_msg)
                raise Exception(f"Git clone failed: {error_msg}")

        except Exception as e:
            logger.error("Repository cloning failed",
                        repo=repo_name,
                        error=str(e))
            raise

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
            # Get repository configuration (cached or load it)
            repo_config = self.get_repo_config(repo_name)
            single_queue_required = repo_config.single_queue if repo_config else False
            
            # Determine which container to use
            best_container = None
            
            if single_queue_required:
                # Use the previously assigned container for this single-queue repo
                if repo_name in self.single_queue_assignments:
                    best_container = self.single_queue_assignments[repo_name]
                    logger.info("Using previously assigned container for single-queue repo",
                               repo=repo_name,
                               container=best_container)
                else:
                    # First time for this single-queue repo, assign a container
                    min_queue_size = float('inf')
                    for dev_name in self.config.get_container_pool_list():
                        queue_size = self.container_queues[dev_name].qsize()
                        if queue_size < min_queue_size:
                            min_queue_size = queue_size
                            best_container = dev_name
                    
                    if best_container:
                        self.single_queue_assignments[repo_name] = best_container
                        logger.info("Assigned container for single-queue repo",
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

        # Track container as running
        now = datetime.now(tz=timezone.utc)
        async with self._lock:
            if dev_name not in self.running_containers:
                # First task for this container - record start time
                self.running_containers[dev_name] = {
                    "repo_path": repo_path,
                    "started_at": now,
                    "last_used": now,
                }
            else:
                # Container already running - just update last_used
                self.running_containers[dev_name]["last_used"] = now
                self.running_containers[dev_name]["repo_path"] = repo_path

        try:
            # Get cached config or ensure it's loaded
            devs_options = self.get_repo_config(repo_name)
            if devs_options is None:
                # Not cached yet, need to clone and read config
                logger.info("Repository config not cached, cloning to read DEVS.yml",
                           task_id=queued_task.task_id,
                           container=dev_name,
                           repo_name=repo_name)
                
                devs_options = await self._ensure_repository_cloned(repo_name, repo_path)

                # Cache the repository configuration for future use with hash
                project_name = repo_name.replace('/', '-')
                config_hash = compute_env_config_hash(project_name)
                self.repo_configs[repo_name] = (devs_options, config_hash)

                # Handle single-queue container assignment
                if devs_options and devs_options.single_queue:
                    if repo_name not in self.single_queue_assignments:
                        # This is the first time we've seen this repo needs single-queue
                        # Register it with the current container
                        self.single_queue_assignments[repo_name] = dev_name
                        logger.info("Assigned container for single_queue repo after first clone",
                                   repo=repo_name,
                                   container=dev_name)
                elif repo_name in self.single_queue_assignments:
                    # The repo was previously single-queue but no longer is
                    # Remove it from the assignments tracking
                    previous_container = self.single_queue_assignments[repo_name]
                    del self.single_queue_assignments[repo_name]
                    logger.info("Removed single_queue assignment - DEVS.yml no longer has single_queue=true",
                               repo=repo_name,
                               previously_assigned_container=previous_container)
            else:
                # Config already cached, just ensure repository is cloned without re-reading config
                logger.info("Using cached repository config, ensuring repo is cloned",
                           task_id=queued_task.task_id,
                           container=dev_name,
                           repo_name=repo_name)
                
                # Still need to ensure the repository files are available locally
                # but we can skip re-reading DEVS.yml
                await self._ensure_repository_files_available(repo_name, repo_path)
            
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

            # Add worker logs directory if enabled
            if self.config.worker_logs_enabled:
                cmd.extend(["--worker-logs-dir", str(self.config.worker_logs_dir)])

            # Determine log file path for logging
            worker_log_file = None
            if self.config.worker_logs_enabled:
                worker_log_file = str(self.config.worker_logs_dir / f"{queued_task.task_id}.log")

            logger.info("Launching worker subprocess",
                       task_id=queued_task.task_id,
                       container=dev_name,
                       command_length=len(' '.join(cmd)),
                       stdin_payload_size=len(stdin_json),
                       worker_log_file=worker_log_file)

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
                    stdout_content = stdout.decode('utf-8', errors='replace') if stdout else ''
                    stderr_content = stderr.decode('utf-8', errors='replace') if stderr else ''
                    
                    logger.info("Subprocess task completed successfully",
                               task_id=queued_task.task_id,
                               container=dev_name,
                               return_code=process.returncode)
                    
                    # Log stdout and stderr for debugging (even on success)
                    if stdout_content:
                        logger.info("Subprocess stdout",
                                   task_id=queued_task.task_id,
                                   container=dev_name,
                                   stdout=stdout_content[:2000])  # First 2000 chars
                    
                    if stderr_content:
                        logger.info("Subprocess stderr",
                                   task_id=queued_task.task_id, 
                                   container=dev_name,
                                   stderr=stderr_content[:8000])  # First 8000 chars for debugging
                    
                    # Try to extract Claude's output from JSON if possible (for logging)
                    try:
                        result_data = json.loads(stdout_content)
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
                    
                    # Log stdout and stderr for debugging
                    if stdout_content:
                        logger.error("Subprocess stdout",
                                    task_id=queued_task.task_id,
                                    container=dev_name,
                                    stdout=stdout_content[:2000])  # First 2000 chars
                    
                    if stderr_content:
                        logger.error("Subprocess stderr", 
                                    task_id=queued_task.task_id,
                                    container=dev_name,
                                    stderr=stderr_content[:2000])  # First 2000 chars
                    
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

        finally:
            # Update last_used timestamp after task completes (success or failure)
            async with self._lock:
                if dev_name in self.running_containers:
                    self.running_containers[dev_name]["last_used"] = datetime.now(tz=timezone.utc)

    async def _checkout_default_branch(self, repo_name: str, repo_path: Path) -> None:
        """Checkout the default branch to ensure devcontainer files are from the right branch.

        Uses the default_branch from user-specific DEVS.yml config if available,
        otherwise tries "dev", then "main".

        Args:
            repo_name: Repository name (owner/repo)
            repo_path: Path to the cloned repository
        """
        # Try to get default_branch from user config (no need to read repo config yet)
        user_config = self._try_load_user_config(repo_name)
        if user_config and user_config.default_branch:
            default_branch = user_config.default_branch
        else:
            default_branch = "dev"  # Try dev first, fall back to main

        logger.info("Checking out default branch for devcontainer",
                   repo=repo_name,
                   branch=default_branch)

        # Try to checkout the branch (use -f to discard local modifications from previous runs)
        checkout_cmd = ["git", "-C", str(repo_path), "checkout", "-f", default_branch]
        process = await asyncio.create_subprocess_exec(
            *checkout_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("Checked out default branch",
                       repo=repo_name,
                       branch=default_branch)
        elif default_branch == "dev":
            # dev branch doesn't exist, try main
            logger.info("Branch 'dev' not found, trying 'main'",
                       repo=repo_name)
            checkout_cmd = ["git", "-C", str(repo_path), "checkout", "-f", "main"]
            process = await asyncio.create_subprocess_exec(
                *checkout_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("Checked out main branch",
                           repo=repo_name)
            else:
                # Both failed, stay on current branch (probably master or main after clone)
                logger.warning("Could not checkout dev or main branch, staying on current branch",
                              repo=repo_name,
                              stderr=stderr.decode()[:200] if stderr else "")
        else:
            # Specified branch doesn't exist
            logger.warning("Could not checkout branch, staying on current branch",
                          repo=repo_name,
                          branch=default_branch,
                          stderr=stderr.decode()[:200] if stderr else "")

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
                logger.info("Repository exists, fetching latest changes",
                           repo=repo_name,
                           repo_path=str(repo_path))
                
                # Set up authentication for private repos
                if self.config.github_token:
                    # Configure the token for this specific repo
                    remote_url = f"https://{self.config.github_token}@github.com/{repo_name}.git"
                    set_remote_cmd = ["git", "-C", str(repo_path), "remote", "set-url", "origin", remote_url]
                    await asyncio.create_subprocess_exec(*set_remote_cmd)
                
                # Fetch all branches to ensure we have all commits
                cmd = ["git", "-C", str(repo_path), "fetch", "--all"]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    logger.info("Git fetch succeeded",
                               repo=repo_name,
                               stdout=stdout.decode()[:200] if stdout else "")

                    # Checkout the default branch to ensure devcontainer files are from the right branch
                    await self._checkout_default_branch(repo_name, repo_path)

                    logger.info("Repository updated", repo=repo_name, path=str(repo_path))
                else:
                    # Fetch failed - remove and re-clone
                    logger.warning("Git fetch failed, removing and re-cloning",
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

                    # Checkout the default branch to ensure devcontainer files are from the right branch
                    await self._checkout_default_branch(repo_name, repo_path)
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

        # Cancel the cleanup worker (if enabled)
        if self.cleanup_worker is not None:
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
            github_client = GitHubClient(self.config)
            
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
            now = datetime.now(tz=timezone.utc)
            return {
                "container_queues": {
                    name: queue.qsize()
                    for name, queue in self.container_queues.items()
                },
                "running_containers": {
                    name: {
                        "repo_path": str(info["repo_path"]),
                        "started_at": info["started_at"].isoformat(),
                        "last_used": info["last_used"].isoformat(),
                        "age_hours": round((now - info["started_at"]).total_seconds() / 3600, 2),
                        "idle_minutes": round((now - info["last_used"]).total_seconds() / 60, 2),
                    }
                    for name, info in self.running_containers.items()
                },
                "total_containers": len(self.config.get_container_pool_list()),
                "single_queue_assignments": self.single_queue_assignments.copy(),
                "cached_repo_configs": list(self.repo_configs.keys()),
                "cleanup_settings": {
                    "idle_timeout_minutes": self.config.container_timeout_minutes,
                    "max_age_hours": self.config.container_max_age_hours,
                    "check_interval_seconds": self.config.cleanup_check_interval_seconds,
                },
            }

    async def force_stop_container(self, container_name: str) -> bool:
        """Force stop a container immediately.

        This method stops a container regardless of whether it's currently processing
        a task. Use with caution - any running task will be interrupted.

        Args:
            container_name: Name of the container to stop

        Returns:
            True if container was found and stopped, False otherwise
        """
        async with self._lock:
            if container_name not in self.running_containers:
                logger.warning("Container not found for force stop",
                              container=container_name,
                              available=list(self.running_containers.keys()))
                return False

            info = self.running_containers[container_name]
            repo_path = info["repo_path"]

            logger.info("Force stopping container",
                       container=container_name,
                       repo_path=str(repo_path))

            try:
                await self._cleanup_container(container_name, repo_path)
                del self.running_containers[container_name]

                logger.info("Container force stopped successfully",
                           container=container_name)
                return True

            except Exception as e:
                logger.error("Failed to force stop container",
                            container=container_name,
                            error=str(e))
                return False

    def get_total_queued_tasks(self) -> int:
        """Get the total number of tasks queued across all containers.

        Returns:
            Total number of tasks waiting in all queues
        """
        return sum(queue.qsize() for queue in self.container_queues.values())

    async def wait_for_all_tasks_complete(self, timeout: Optional[float] = None) -> bool:
        """Wait for all queued tasks to be processed.

        This waits for all container queues to be fully drained, meaning
        all tasks have been picked up by workers AND task_done() has been
        called for each (i.e., processing is complete, not just started).

        Args:
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            True if all tasks completed, False if timeout occurred.
        """
        logger.info("Waiting for all container queues to drain",
                   queues={name: q.qsize() for name, q in self.container_queues.items()})

        async def wait_all_queues():
            # Wait for each queue to be fully processed
            # asyncio.Queue.join() waits until all items have had task_done() called
            wait_tasks = [
                queue.join()
                for queue in self.container_queues.values()
            ]
            await asyncio.gather(*wait_tasks)

        try:
            if timeout is not None:
                await asyncio.wait_for(wait_all_queues(), timeout=timeout)
            else:
                await wait_all_queues()

            logger.info("All container queues drained successfully")
            return True

        except asyncio.TimeoutError:
            remaining = {name: q.qsize() for name, q in self.container_queues.items()}
            logger.warning("Timeout waiting for queues to drain",
                          remaining_tasks=remaining,
                          timeout_seconds=timeout)
            return False

    async def _idle_cleanup_worker(self) -> None:
        """Periodically clean up idle and old containers.

        Containers are cleaned up if:
        1. They have been idle longer than container_timeout_minutes
        2. They are older than container_max_age_hours AND currently idle

        Containers that are currently processing a task are never stopped,
        even if they exceed the max age.
        """
        while True:
            try:
                await asyncio.sleep(self.config.cleanup_check_interval_seconds)

                async with self._lock:
                    now = datetime.now(tz=timezone.utc)
                    idle_timeout = timedelta(minutes=self.config.container_timeout_minutes)
                    max_age = timedelta(hours=self.config.container_max_age_hours)

                    containers_to_cleanup = []
                    for dev_name, info in self.running_containers.items():
                        idle_duration = now - info["last_used"]
                        age = now - info["started_at"]

                        # Check if container is idle (not currently processing)
                        is_idle = idle_duration > timedelta(seconds=10)  # Small grace period

                        # Clean up if: idle too long OR (old AND idle)
                        if idle_duration > idle_timeout:
                            logger.info("Container idle timeout exceeded",
                                       container=dev_name,
                                       idle_minutes=idle_duration.total_seconds() / 60)
                            containers_to_cleanup.append((dev_name, info["repo_path"]))
                        elif age > max_age and is_idle:
                            logger.info("Container max age exceeded (cleaning up while idle)",
                                       container=dev_name,
                                       age_hours=age.total_seconds() / 3600,
                                       max_age_hours=self.config.container_max_age_hours)
                            containers_to_cleanup.append((dev_name, info["repo_path"]))

                    for dev_name, repo_path in containers_to_cleanup:
                        logger.info("Cleaning up container", container=dev_name)
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