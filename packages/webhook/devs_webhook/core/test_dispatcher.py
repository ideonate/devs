"""Test runner dispatcher for executing CI tests in containers."""

import uuid
from typing import Optional
import structlog
from pathlib import Path

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from ..github.models import WebhookEvent, PushEvent, PullRequestEvent
from devs_common.devs_config import DevsOptions
from .base_dispatcher import BaseDispatcher, TaskResult
from ..utils.container_logs import create_container_log_writer
from ..utils.s3_artifacts import create_s3_uploader_from_config

logger = structlog.get_logger()


class TestDispatcher(BaseDispatcher):
    """Dispatches test commands to containers and reports results via GitHub Checks API."""

    dispatcher_name = "Test"

    def __init__(self):
        """Initialize test dispatcher."""
        super().__init__("test")
        # Track last artifact URL for passing to Checks API
        self._last_artifact_url: Optional[str] = None
        # Track combined report.md content for passing to Checks API
        self._last_report_content: Optional[str] = None
        # Track worker log URL for passing to Checks API
        self._last_worker_log_url: Optional[str] = None
    
    async def execute_task(
        self,
        dev_name: str,
        repo_path: Path,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        worker_log_path: Optional[str] = None
    ) -> TaskResult:
        """Execute tests using container and report results via GitHub Checks API.

        Args:
            dev_name: Name of dev container (e.g., eamonn)
            repo_path: Path to repository on host (already calculated by container_pool)
            event: Original webhook event
            devs_options: Options from DEVS.yml file
            task_description: Task description (ignored by test dispatcher)
            task_id: Optional task identifier for logging
            worker_log_path: Optional path to worker log file (for including in failure messages)

        Returns:
            Test execution result
        """
        # Store worker_log_path for use in failure messages
        self._worker_log_path = worker_log_path
        # Generate task_id if not provided
        if not task_id:
            task_id = str(uuid.uuid4())[:8]

        check_run_id = None
        # Reset artifact URL, report content, and worker log URL for this task
        self._last_artifact_url = None
        self._last_report_content = None
        self._last_worker_log_url = None

        try:
            logger.info("Starting test execution",
                       container=dev_name,
                       repo=event.repository.full_name,
                       repo_path=str(repo_path),
                       task_id=task_id)
            
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
                devs_options,
                task_id=task_id
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
                    installation_id,
                    details_url=self._last_artifact_url,
                    report_content=self._last_report_content,
                    worker_log_url=self._last_worker_log_url
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
                
                summary = f"An error occurred during test execution: {error_msg}"
                if hasattr(self, '_worker_log_path') and self._worker_log_path:
                    summary += f"\n\nWorker log: `{self._worker_log_path}`"

                await self.github_client.complete_check_run_failure(
                    repo=event.repository.full_name,
                    check_run_id=check_run_id,
                    title="Test execution failed",
                    summary=summary,
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
        devs_options: Optional[DevsOptions] = None,
        task_id: Optional[str] = None
    ) -> tuple[bool, str, str, int]:
        """Execute tests synchronously in container.

        Args:
            repo_path: Path to repository
            dev_name: Development environment name
            event: Webhook event
            devs_options: Options from DEVS.yml
            task_id: Optional task identifier for logging

        Returns:
            Tuple of (success, stdout, stderr, exit_code)
        """
        # Create container log writer if enabled
        container_log = create_container_log_writer(
            config=self.config,
            container_name=dev_name,
            task_id=task_id or str(uuid.uuid4())[:8],
            repo_name=event.repository.full_name,
            task_type="tests"
        )

        try:
            # 1. Create project, workspace manager, and container manager
            project = Project(repo_path)
            workspace_manager = WorkspaceManager(project, self.config)
            container_manager = ContainerManager(project, self.config)
            
            logger.info("Created project and managers for tests",
                       container=dev_name,
                       project_name=project.info.name)
            
            # 2. Ensure workspace exists and sync code
            # Don't use reset_contents=True as it deletes files created by postCreateCommand
            # (e.g., backend/.env). Instead, create workspace if needed, then sync git-tracked files.
            if workspace_manager.workspace_exists(dev_name):
                workspace_dir = workspace_manager.get_workspace_dir(dev_name)
                workspace_manager.sync_workspace(dev_name)
                logger.info("Synced existing workspace for tests",
                           container=dev_name,
                           workspace_dir=str(workspace_dir))
            else:
                workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=False)
                logger.info("Created new workspace for tests",
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
                # For PRs, we need to fetch the PR branch first since the commit
                # may not be available locally (especially for fork PRs)
                if isinstance(event, PullRequestEvent):
                    pr_number = event.pull_request.number
                    head_ref = event.pull_request.head.get("ref")

                    logger.info("Fetching PR branch before checkout",
                               container=dev_name,
                               pr_number=pr_number,
                               head_ref=head_ref,
                               commit_sha=commit_sha)

                    # Fetch the PR head using GitHub's special refs
                    # This works for both same-repo and fork PRs
                    fetch_success, fetch_stdout, fetch_stderr, fetch_code = container_manager.exec_command(
                        dev_name=dev_name,
                        workspace_dir=workspace_dir,
                        command=f"git fetch origin pull/{pr_number}/head",
                        debug=self.config.dev_mode,
                        stream=False,
                        extra_env=extra_env
                    )

                    if not fetch_success:
                        logger.error("Failed to fetch PR branch",
                                   container=dev_name,
                                   pr_number=pr_number,
                                   stderr=fetch_stderr)
                        return False, fetch_stdout, f"Failed to fetch PR #{pr_number}: {fetch_stderr}", fetch_code

                    logger.info("Successfully fetched PR branch",
                               container=dev_name,
                               pr_number=pr_number)

                elif isinstance(event, PushEvent):
                    # For push events, fetch the branch to ensure commit is available
                    branch_ref = event.ref
                    # Extract branch name from refs/heads/branch-name
                    branch_name = branch_ref.replace("refs/heads/", "") if branch_ref.startswith("refs/heads/") else branch_ref

                    logger.info("Fetching branch before checkout",
                               container=dev_name,
                               branch_ref=branch_ref,
                               branch_name=branch_name,
                               commit_sha=commit_sha)

                    fetch_success, fetch_stdout, fetch_stderr, fetch_code = container_manager.exec_command(
                        dev_name=dev_name,
                        workspace_dir=workspace_dir,
                        command=f"git fetch origin {branch_name}",
                        debug=self.config.dev_mode,
                        stream=False,
                        extra_env=extra_env
                    )

                    if not fetch_success:
                        logger.error("Failed to fetch branch",
                                   container=dev_name,
                                   branch_name=branch_name,
                                   stderr=fetch_stderr)
                        return False, fetch_stdout, f"Failed to fetch branch {branch_name}: {fetch_stderr}", fetch_code

                    logger.info("Successfully fetched branch",
                               container=dev_name,
                               branch_name=branch_name)

                logger.info("Checking out commit for tests",
                           container=dev_name,
                           commit_sha=commit_sha)

                # Use -f to force checkout and discard any local modifications
                # from previous test runs (workspace may have leftover changes)
                checkout_success, checkout_stdout, checkout_stderr, checkout_code = container_manager.exec_command(
                    dev_name=dev_name,
                    workspace_dir=workspace_dir,
                    command=f"git checkout -f {commit_sha}",
                    debug=self.config.dev_mode,
                    stream=False,
                    extra_env=extra_env
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

            # Start container logging if enabled
            if container_log:
                container_log.start(test_command=test_command, workspace_dir=str(workspace_dir))

            # 6. Execute tests
            success, stdout, stderr, exit_code = container_manager.exec_command(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                command=test_command,
                debug=self.config.dev_mode,
                stream=False,
                extra_env=extra_env
            )

            # Write container output to log file if enabled
            if container_log:
                container_log.write_output(stdout, stderr)
                container_log.end(
                    success=success,
                    exit_code=exit_code,
                    error=stderr if not success else None
                )

            logger.info("Test command completed",
                       container=dev_name,
                       success=success,
                       exit_code=exit_code,
                       output_length=len(stdout) if stdout else 0,
                       error_length=len(stderr) if stderr else 0)

            # Log full output for debugging (useful in worker logs)
            if stdout:
                logger.info("Test stdout",
                           container=dev_name,
                           full_stdout=stdout)
            if stderr:
                logger.info("Test stderr",
                           container=dev_name,
                           full_stderr=stderr)

            # 7. Collect report.md files from test-results/ for Checks API
            self._last_report_content = self._collect_report_markdown(
                container_manager=container_manager,
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                extra_env=extra_env
            )

            # 8. Upload artifacts to S3 if configured
            effective_task_id = task_id or str(uuid.uuid4())[:8]
            s3_url, artifact_url = self._upload_bridge_artifacts(
                project=project,
                dev_name=dev_name,
                repo_name=event.repository.full_name,
                task_id=effective_task_id
            )
            if s3_url:
                logger.info("Test artifacts uploaded to S3",
                           container=dev_name,
                           s3_url=s3_url,
                           artifact_url=artifact_url)

            # Return artifact_url as part of success tuple for use in Checks API
            # We'll store it as instance variable for access in execute_task
            self._last_artifact_url = artifact_url

            # 9. Upload worker log file to S3 if configured and available
            worker_log_url = self._upload_worker_log(
                worker_log_path=self._worker_log_path,
                repo_name=event.repository.full_name,
                task_id=effective_task_id,
                dev_name=dev_name
            )
            if worker_log_url:
                self._last_worker_log_url = worker_log_url
                logger.info("Worker log uploaded to S3",
                           container=dev_name,
                           worker_log_url=worker_log_url)

            return success, stdout, stderr, exit_code

        except Exception as e:
            error_msg = f"Test execution failed: {str(e)}"
            logger.error("Test execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)

            # Log the error to container log if enabled
            if container_log:
                container_log.end(success=False, exit_code=1, error=error_msg)

            return False, "", error_msg, 1
    
    def _collect_report_markdown(
        self,
        container_manager: ContainerManager,
        dev_name: str,
        workspace_dir: Path,
        extra_env: Optional[dict] = None
    ) -> Optional[str]:
        """Collect all report.md files from test-results/ directory in the container.

        Searches for report.md files recursively up to 2 levels deep in test-results/
        and combines their contents.

        Args:
            container_manager: Container manager instance
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            extra_env: Optional extra environment variables

        Returns:
            Combined markdown content from all report.md files, or None if none found
        """
        try:
            # Find all report.md files in test-results/ (2 levels deep)
            find_cmd = "find test-results -maxdepth 2 -name 'report.md' -type f 2>/dev/null | sort"
            success, stdout, stderr, exit_code = container_manager.exec_command(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                command=find_cmd,
                debug=self.config.dev_mode,
                stream=False,
                extra_env=extra_env
            )

            if not success or not stdout.strip():
                logger.debug("No report.md files found in test-results/",
                            container=dev_name)
                return None

            report_files = stdout.strip().split('\n')
            logger.info("Found report.md files",
                       container=dev_name,
                       files=report_files)

            # Collect contents from each report file
            combined_parts = []
            for report_file in report_files:
                if not report_file.strip():
                    continue

                cat_cmd = f"cat '{report_file}'"
                cat_success, content, cat_stderr, cat_code = container_manager.exec_command(
                    dev_name=dev_name,
                    workspace_dir=workspace_dir,
                    command=cat_cmd,
                    debug=self.config.dev_mode,
                    stream=False,
                    extra_env=extra_env
                )

                if cat_success and content.strip():
                    # Add header for each report file
                    header = f"## {report_file}\n"
                    combined_parts.append(header + content.strip())
                    logger.debug("Collected report content",
                               container=dev_name,
                               file=report_file,
                               content_length=len(content))

            if not combined_parts:
                return None

            combined_content = "\n\n---\n\n".join(combined_parts)
            logger.info("Combined report.md content",
                       container=dev_name,
                       num_files=len(combined_parts),
                       total_length=len(combined_content))

            return combined_content

        except Exception as e:
            logger.warning("Failed to collect report.md files",
                          container=dev_name,
                          error=str(e))
            return None

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
        installation_id: Optional[str] = None,
        details_url: Optional[str] = None,
        report_content: Optional[str] = None,
        worker_log_url: Optional[str] = None
    ) -> None:
        """Report test results to GitHub via Checks API.

        Args:
            repo_name: Repository name (owner/repo)
            check_run_id: GitHub check run ID
            result: Test execution result
            installation_id: GitHub App installation ID if known from webhook event
            details_url: URL to test artifacts/details (shown as "View more details" link)
            report_content: Combined content from report.md files in test-results/
            worker_log_url: URL to uploaded worker log file (if available)
        """
        try:
            if result.success:
                summary = f"All tests completed successfully (exit code: {result.exit_code})"
                if details_url:
                    summary += f"\n\n[View test artifacts]({details_url})"
                if worker_log_url:
                    summary += f"\n\n[View worker log]({worker_log_url})"
                if hasattr(self, '_worker_log_path') and self._worker_log_path:
                    summary += f"\n\nWorker log path: `{self._worker_log_path}`"

                # Truncate report content for GitHub API limits (~65k chars)
                text = report_content
                if text and len(text) > 65000:
                    text = text[:65000] + "\n\n[Report truncated]"

                await self.github_client.complete_check_run_success(
                    repo=repo_name,
                    check_run_id=check_run_id,
                    title="Tests passed",
                    summary=summary,
                    text=text,
                    details_url=details_url,
                    installation_id=installation_id
                )
                logger.info("Reported test success to GitHub",
                           repo=repo_name,
                           check_run_id=check_run_id,
                           details_url=details_url,
                           worker_log_url=worker_log_url,
                           has_report_content=bool(report_content))
            else:
                # Combine report content with stdout/stderr for failure output
                text_parts = []

                # Add report.md content first if available
                if report_content:
                    text_parts.append(report_content)
                    text_parts.append("\n---\n\n## Command Output\n")

                # Add stdout and stderr
                if result.output:
                    text_parts.append(result.output)
                if result.error:
                    text_parts.append(result.error)

                error_text = "\n".join(text_parts) if text_parts else "Test execution failed"

                # Truncate for GitHub API limits (~65k chars)
                if len(error_text) > 65000:
                    error_text = error_text[:65000] + "\n\n[Output truncated]"

                summary = f"Tests failed with exit code: {result.exit_code}"
                if details_url:
                    summary += f"\n\n[View test artifacts]({details_url})"
                if worker_log_url:
                    summary += f"\n\n[View worker log]({worker_log_url})"
                if hasattr(self, '_worker_log_path') and self._worker_log_path:
                    summary += f"\n\nWorker log path: `{self._worker_log_path}`"

                await self.github_client.complete_check_run_failure(
                    repo=repo_name,
                    check_run_id=check_run_id,
                    title="Tests failed",
                    summary=summary,
                    text=error_text,
                    details_url=details_url,
                    installation_id=installation_id
                )
                logger.info("Reported test failure to GitHub",
                           repo=repo_name,
                           check_run_id=check_run_id,
                           exit_code=result.exit_code,
                           details_url=details_url,
                           worker_log_url=worker_log_url,
                           has_report_content=bool(report_content))

        except Exception as e:
            logger.error("Failed to report test results to GitHub",
                        repo=repo_name,
                        check_run_id=check_run_id,
                        error=str(e))
    
    def _upload_bridge_artifacts(
        self,
        project: Project,
        dev_name: str,
        repo_name: str,
        task_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Upload bridge directory contents to S3 as a tar.gz archive.

        Args:
            project: Project instance
            dev_name: Development environment name
            repo_name: Repository name (owner/repo format)
            task_id: Unique task identifier

        Returns:
            Tuple of (s3_url, public_url):
                - s3_url: S3 URL of uploaded artifact (s3://bucket/key)
                - public_url: Public HTTP URL if configured, for sharing via Checks API
            Both are None if upload skipped/failed.
        """
        # Check if S3 artifact upload is configured
        s3_uploader = create_s3_uploader_from_config(self.config)
        if not s3_uploader:
            logger.debug("S3 artifact upload not configured, skipping")
            return None, None

        # Get bridge directory path for this project/dev combination
        bridge_dir = self.config.bridge_dir / f"{project.info.name}-{dev_name}"

        logger.info("Attempting to upload bridge artifacts",
                   bridge_dir=str(bridge_dir),
                   repo_name=repo_name,
                   task_id=task_id)

        return s3_uploader.upload_directory_as_tar(
            directory=bridge_dir,
            repo_name=repo_name,
            task_id=task_id,
            dev_name=dev_name,
            task_type="tests"
        )

    def _upload_worker_log(
        self,
        worker_log_path: Optional[str],
        repo_name: str,
        task_id: str,
        dev_name: str
    ) -> Optional[str]:
        """Upload worker log file to S3 if available.

        Args:
            worker_log_path: Path to worker log file (may be None)
            repo_name: Repository name (owner/repo format)
            task_id: Unique task identifier
            dev_name: Development environment name

        Returns:
            Public URL to the uploaded log file, or None if upload skipped/failed.
        """
        if not worker_log_path:
            logger.debug("No worker log path provided, skipping upload")
            return None

        # Check if S3 artifact upload is configured
        s3_uploader = create_s3_uploader_from_config(self.config)
        if not s3_uploader:
            logger.debug("S3 artifact upload not configured, skipping worker log upload")
            return None

        log_path = Path(worker_log_path)
        if not log_path.exists():
            logger.warning("Worker log file does not exist, skipping upload",
                          worker_log_path=worker_log_path)
            return None

        logger.info("Attempting to upload worker log",
                   worker_log_path=worker_log_path,
                   repo_name=repo_name,
                   task_id=task_id)

        s3_url, public_url = s3_uploader.upload_file(
            file_path=log_path,
            repo_name=repo_name,
            task_id=task_id,
            dev_name=dev_name,
            task_type="tests",
            file_suffix="-worker"
        )

        return public_url