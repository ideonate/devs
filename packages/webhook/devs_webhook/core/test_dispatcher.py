"""Test runner dispatcher for executing CI tests in containers."""

from typing import Optional
import structlog
from pathlib import Path

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from ..github.models import WebhookEvent, PushEvent, PullRequestEvent
from devs_common.devs_config import DevsOptions
from .base_dispatcher import BaseDispatcher, TaskResult

logger = structlog.get_logger()


class TestDispatcher(BaseDispatcher):
    """Dispatches test commands to containers and reports results via GitHub Checks API."""
    
    dispatcher_name = "Test"
    
    def __init__(self):
        """Initialize test dispatcher."""
        super().__init__("test")
    
    async def execute_task(
        self,
        dev_name: str,
        repo_path: Path,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None,
        task_description: Optional[str] = None
    ) -> TaskResult:
        """Execute tests using container and report results via GitHub Checks API.
        
        Args:
            dev_name: Name of dev container (e.g., eamonn)
            repo_path: Path to repository on host (already calculated by container_pool)
            event: Original webhook event
            devs_options: Options from DEVS.yml file
            task_description: Task description (ignored by test dispatcher)
            
        Returns:
            Test execution result
        """
        check_run_id = None
        
        try:
            logger.info("Starting test execution",
                       container=dev_name,
                       repo=event.repository.full_name,
                       repo_path=str(repo_path))
            
            # Determine the commit SHA to test
            commit_sha = self._get_commit_sha(event)
            logger.info("Commit SHA determination result", commit_sha=commit_sha)
            
            if not commit_sha:
                logger.error("Could not determine commit SHA, using fallback for testing")
                # Use a fallback SHA for testing - in real scenarios this shouldn't happen
                commit_sha = "HEAD"  # Fallback to HEAD for now
            
            # Create GitHub check run
            # Safely extract installation ID, handling potential encoding issues
            installation_id = None
            try:
                if event.installation and hasattr(event.installation, 'id') and event.installation.id is not None:
                    installation_id = str(event.installation.id)
                    logger.info("Extracted installation ID from event", installation_id=installation_id)
                else:
                    logger.warning("No installation ID found in event")
            except (AttributeError, TypeError, ValueError) as e:
                logger.warning("Could not extract installation ID", error=str(e))
                installation_id = None
            
            # Skip GitHub API calls for test events or in dev mode
            if hasattr(event, 'is_test') and event.is_test:
                logger.info("Skipping GitHub check run creation for test event")
                check_run_id = None
            else:
                logger.info("About to create GitHub check run", 
                           repo=event.repository.full_name,
                           commit_sha=commit_sha,
                           installation_id=installation_id)
                
                check_run_id = await self.github_client.create_check_run(
                    repo=event.repository.full_name,
                    name="devs-ci",
                    head_sha=commit_sha,
                    status="in_progress",
                    installation_id=installation_id
                )
                
                logger.info("GitHub check run creation attempt completed", 
                           check_run_id=check_run_id,
                           success=check_run_id is not None)
            
            if check_run_id:
                logger.info("Created GitHub check run",
                           repo=event.repository.full_name,
                           check_run_id=check_run_id,
                           commit_sha=commit_sha)
            
            # Execute tests
            success, output, error, exit_code = self._execute_tests_sync(
                repo_path,
                dev_name,
                event,
                devs_options
            )
            
            # Build result
            result = TaskResult(
                success=success,
                output=output,
                error=error if not success else None,
                exit_code=exit_code
            )
            
            # Report results to GitHub
            if check_run_id:
                # Safely extract installation ID, handling potential encoding issues
                installation_id = None
                try:
                    if event.installation and hasattr(event.installation, 'id') and event.installation.id is not None:
                        installation_id = str(event.installation.id)
                except (AttributeError, TypeError, ValueError) as e:
                    logger.warning("Could not extract installation ID", error=str(e))
                    installation_id = None
                
                await self._report_test_results(
                    event.repository.full_name,
                    check_run_id,
                    result,
                    installation_id
                )
            elif hasattr(event, 'is_test') and event.is_test:
                logger.info("Skipping GitHub check run result reporting for test event")
            
            if result.success:
                logger.info("Test execution completed successfully",
                           container=dev_name,
                           repo=event.repository.full_name,
                           exit_code=exit_code)
            else:
                logger.error("Test execution failed",
                           container=dev_name,
                           repo=event.repository.full_name,
                           exit_code=exit_code,
                           error=result.error)
            
            return result
                
        except Exception as e:
            error_msg = f"Test execution failed: {str(e)}"
            logger.error("Test execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)
            
            # Report failure to GitHub if we created a check run
            if check_run_id:
                # Safely extract installation ID, handling potential encoding issues
                installation_id = None
                try:
                    if event.installation and hasattr(event.installation, 'id') and event.installation.id is not None:
                        installation_id = str(event.installation.id)
                except (AttributeError, TypeError, ValueError) as e:
                    logger.warning("Could not extract installation ID", error=str(e))
                    installation_id = None
                
                await self.github_client.complete_check_run_failure(
                    repo=event.repository.full_name,
                    check_run_id=check_run_id,
                    title="Test execution failed",
                    summary=f"An error occurred during test execution: {error_msg}",
                    installation_id=installation_id
                )
            elif hasattr(event, 'is_test') and event.is_test:
                logger.info("Skipping GitHub check run failure reporting for test event")
            
            return TaskResult(success=False, output="", error=error_msg)
    
    def _execute_tests_sync(
        self,
        repo_path: Path,
        dev_name: str,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None
    ) -> tuple[bool, str, str, int]:
        """Execute tests synchronously in container.
        
        Args:
            repo_path: Path to repository
            dev_name: Development environment name
            event: Webhook event
            devs_options: Options from DEVS.yml
            
        Returns:
            Tuple of (success, stdout, stderr, exit_code)
        """
        try:
            # 1. Create project, workspace manager, and container manager
            project = Project(repo_path)
            workspace_manager = WorkspaceManager(project, self.config)
            container_manager = ContainerManager(project, self.config)
            
            logger.info("Created project and managers for tests",
                       container=dev_name,
                       project_name=project.info.name)
            
            # 2. Ensure workspace exists
            workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=True)
            
            logger.info("Workspace created/reset for tests",
                       container=dev_name,
                       workspace_dir=str(workspace_dir))
            
            # 3. Ensure container is running with environment variables from DEVS.yml
            extra_env = None
            if devs_options:
                extra_env = devs_options.get_env_vars(dev_name)
                
            if not container_manager.ensure_container_running(
                dev_name=dev_name, 
                workspace_dir=workspace_dir, 
                force_rebuild=False,
                debug=self.config.dev_mode,
                extra_env=extra_env
            ):
                return False, "", f"Failed to start container for {dev_name}", 1
            
            # 4. Checkout appropriate commit if this is a PR or push
            commit_sha = self._get_commit_sha(event)
            if commit_sha:
                logger.info("Checking out commit for tests",
                           container=dev_name,
                           commit_sha=commit_sha)
                
                checkout_success, checkout_stdout, checkout_stderr, checkout_code = self._exec_command_in_container(
                    project=project,
                    dev_name=dev_name,
                    workspace_dir=workspace_dir,
                    command=f"git checkout {commit_sha}",
                    debug=self.config.dev_mode
                )
                
                if not checkout_success:
                    logger.error("Failed to checkout commit",
                               container=dev_name,
                               commit_sha=commit_sha,
                               stderr=checkout_stderr)
                    return False, checkout_stdout, f"Failed to checkout commit {commit_sha}: {checkout_stderr}", checkout_code
            
            # 5. Determine test command
            test_command = "./runtests.sh"  # Default
            if devs_options and devs_options.ci_test_command:
                test_command = devs_options.ci_test_command
            
            logger.info("Executing test command",
                       container=dev_name,
                       test_command=test_command)
            
            # 6. Execute tests
            success, stdout, stderr, exit_code = self._exec_command_in_container(
                project=project,
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                command=test_command,
                debug=self.config.dev_mode
            )
            
            logger.info("Test command completed",
                       container=dev_name,
                       success=success,
                       exit_code=exit_code,
                       output_length=len(stdout) if stdout else 0,
                       error_length=len(stderr) if stderr else 0)
            
            return success, stdout, stderr, exit_code
            
        except Exception as e:
            error_msg = f"Test execution failed: {str(e)}"
            logger.error("Test execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)
            return False, "", error_msg, 1
    
    def _get_commit_sha(self, event: WebhookEvent) -> Optional[str]:
        """Get the commit SHA to test from the webhook event.
        
        Args:
            event: Webhook event
            
        Returns:
            Commit SHA or None if not available
        """
        logger.info("Extracting commit SHA from event",
                   event_type=type(event).__name__)
        
        if isinstance(event, PushEvent):
            sha = event.after
            logger.info("Got commit SHA from PushEvent", sha=sha)
            return sha
        elif isinstance(event, PullRequestEvent):
            sha = event.pull_request.head.get("sha")
            logger.info("Got commit SHA from PullRequestEvent", 
                       sha=sha, head_keys=list(event.pull_request.head.keys()))
            return sha
        else:
            logger.warning("Event type not supported for commit SHA extraction",
                          event_type=type(event).__name__)
            return None
    
    async def _report_test_results(
        self,
        repo_name: str,
        check_run_id: int,
        result: TaskResult,
        installation_id: Optional[str] = None
    ) -> None:
        """Report test results to GitHub via Checks API.
        
        Args:
            repo_name: Repository name (owner/repo)
            check_run_id: GitHub check run ID
            result: Test execution result
            installation_id: GitHub App installation ID if known from webhook event
        """
        try:
            if result.success:
                await self.github_client.complete_check_run_success(
                    repo=repo_name,
                    check_run_id=check_run_id,
                    title="Tests passed",
                    summary=f"All tests completed successfully (exit code: {result.exit_code})",
                    installation_id=installation_id
                )
                logger.info("Reported test success to GitHub",
                           repo=repo_name,
                           check_run_id=check_run_id)
            else:
                # Truncate output for GitHub (limit to ~65k chars to stay under API limits)
                error_text = result.error or result.output or "Test execution failed"
                if len(error_text) > 65000:
                    error_text = error_text[:65000] + "\n\n[Output truncated]"
                
                await self.github_client.complete_check_run_failure(
                    repo=repo_name,
                    check_run_id=check_run_id,
                    title="Tests failed",
                    summary=f"Tests failed with exit code: {result.exit_code}",
                    text=error_text,
                    installation_id=installation_id
                )
                logger.info("Reported test failure to GitHub",
                           repo=repo_name,
                           check_run_id=check_run_id,
                           exit_code=result.exit_code)
                
        except Exception as e:
            logger.error("Failed to report test results to GitHub",
                        repo=repo_name,
                        check_run_id=check_run_id,
                        error=str(e))
    
    def _exec_command_in_container(
        self,
        project: Project,
        dev_name: str,
        workspace_dir: Path,
        command: str,
        debug: bool = False
    ) -> tuple[bool, str, str, int]:
        """Execute a command in the container.
        
        Args:
            project: Project instance
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            command: Command to execute
            debug: Show debug output
            
        Returns:
            Tuple of (success, stdout, stderr, exit_code)
        """
        import subprocess
        
        # Use ContainerManager to get container info consistently
        container_manager = ContainerManager(project, self.config)
        container_info = container_manager._get_container_info(dev_name)
        container_name = container_info["container_name"]
        container_workspace_dir = container_info["container_workspace_dir"]
        
        try:
            # Execute command in the container
            # Use same pattern as exec_claude: cd to workspace directory then run command
            full_cmd = f"source ~/.zshrc >/dev/stderr 2>&1 && cd {container_workspace_dir} && {command}"
            cmd = [
                'docker', 'exec', '-i',  # -i for stdin, no TTY
                container_name,
                '/bin/zsh', '-c', full_cmd  # Use zsh with explicit sourcing
            ]
            
            if debug:
                logger.info("Executing command in container",
                           container=container_name,
                           command=command,
                           full_command=' '.join(cmd))
            
            # Execute command without streaming (for CI we want to collect all output)
            process = subprocess.run(
                cmd, 
                capture_output=True,
                text=True
            )
            
            stdout = process.stdout if process.stdout else ""
            stderr = process.stderr if process.stderr else ""
            success = process.returncode == 0
            exit_code = process.returncode
            
            if debug:
                logger.info("Command execution completed",
                           container=container_name,
                           command=command,
                           exit_code=exit_code,
                           success=success,
                           stdout_length=len(stdout),
                           stderr_length=len(stderr))
            
            return success, stdout, stderr, exit_code
            
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            logger.error("Error executing command in container",
                        container=container_name,
                        command=command,
                        error=error_msg,
                        exc_info=True)
            return False, "", error_msg, 1