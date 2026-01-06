"""Claude Code CLI integration for executing tasks in containers."""

import uuid
from typing import Optional
import structlog
from pathlib import Path

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from ..github.models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent
from devs_common.devs_config import DevsOptions
from .base_dispatcher import BaseDispatcher, TaskResult
from ..utils.container_logs import create_container_log_writer

logger = structlog.get_logger()


class ClaudeDispatcher(BaseDispatcher):
    """Dispatches tasks to Claude Code CLI running in containers."""
    
    dispatcher_name = "Claude"
    
    def __init__(self):
        """Initialize Claude dispatcher."""
        super().__init__("Claude")
    
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
        """Execute a task using Claude Code CLI in a container.

        Args:
            dev_name: Name of dev container (e.g., eamonn)
            repo_path: Path to repository on host (already calculated by container_pool)
            task_description: Task description for Claude
            event: Original webhook event
            devs_options: Options from DEVS.yml file
            task_id: Optional task identifier for logging
            worker_log_path: Optional path to worker log file (for including in failure messages)

        Returns:
            Task execution result
        """
        # Store worker_log_path for use in failure messages
        self._worker_log_path = worker_log_path
        # Generate task_id if not provided
        if not task_id:
            task_id = str(uuid.uuid4())[:8]

        try:
            logger.info("Starting Claude Code CLI task",
                       container=dev_name,
                       repo=event.repository.full_name,
                       repo_path=str(repo_path),
                       task_id=task_id)

            # Execute Claude directly - prompt building, workspace setup, container startup, Claude execution
            # Use task_description if provided, otherwise extract from event
            task_desc = task_description or "Process webhook event"

            success, output, error = self._execute_claude_sync(
                repo_path,
                dev_name,
                task_desc,
                event,
                devs_options,
                task_id=task_id
            )
            
            # Build result - ensure we have meaningful error messages
            if not success:
                # If error is empty but we have output, use output as error
                if not error and output:
                    error = output
                elif not error:
                    error = "Claude execution failed with no error message"
            
            result = TaskResult(
                success=success,
                output=output,
                error=error if not success else None,
                exit_code=None  # Claude doesn't provide exit codes
            )
            
            if result.success:
                # Post-process results
                await self._handle_task_completion(event, result.output)
                logger.info("Claude Code task completed successfully",
                           container=dev_name,
                           repo=event.repository.full_name)
            else:
                # Handle failure
                await self._handle_task_failure(event, result.error or "Unknown error")
                logger.error("Claude Code task failed",
                           container=dev_name,
                           error=result.error)
            
            return result
                
        except Exception as e:
            error_msg = f"Task execution failed: {str(e)}"
            logger.error("Task execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)
            
            await self._handle_task_failure(event, error_msg)
            return TaskResult(success=False, output="", error=error_msg, exit_code=None)
    
    def _execute_claude_sync(
        self,
        repo_path: Path,
        dev_name: str,
        task_description: str,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None,
        task_id: Optional[str] = None
    ) -> tuple[bool, str, str]:
        """Execute complete Claude workflow synchronously.

        This mirrors the CLI approach exactly:
        1. Create project, workspace manager, and container manager
        2. Create/reset workspace (force=True for webhook)
        3. Build prompt
        4. Execute Claude (which handles container startup)

        Args:
            repo_path: Path to repository
            dev_name: Development environment name
            task_description: Task description for Claude
            event: Webhook event
            devs_options: Options from DEVS.yml
            task_id: Optional task identifier for logging

        Returns:
            Tuple of (success, stdout, stderr)
        """
        # Create container log writer if enabled
        container_log = create_container_log_writer(
            config=self.config,
            container_name=dev_name,
            task_id=task_id or str(uuid.uuid4())[:8],
            repo_name=event.repository.full_name,
            task_type="claude"
        )

        try:
            # 1. Create project, workspace manager, and container manager like CLI
            project = Project(repo_path)
            workspace_manager = WorkspaceManager(project, self.config)
            container_manager = ContainerManager(project, self.config)
            
            logger.info("Created project and managers",
                       container=dev_name,
                       project_name=project.info.name)
            
            # 2. Ensure workspace exists and sync code
            # Don't use reset_contents=True as it deletes files created by postCreateCommand
            # (e.g., backend/.env). Instead, create workspace if needed, then sync git-tracked files.
            if workspace_manager.workspace_exists(dev_name):
                workspace_dir = workspace_manager.get_workspace_dir(dev_name)
                workspace_manager.sync_workspace(dev_name)
                logger.info("Synced existing workspace",
                           container=dev_name,
                           workspace_dir=str(workspace_dir))
            else:
                workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=False)
                logger.info("Created new workspace",
                           container=dev_name,
                           workspace_dir=str(workspace_dir))
            
            # 3. Build Claude prompt
            workspace_name = project.get_workspace_name(dev_name)
            workspace_path = f"/workspaces/{workspace_name}"
            repo_name = event.repository.full_name
            
            # Determine if this is a PR or Issue
            is_pr = isinstance(event, PullRequestEvent) or (
                isinstance(event, CommentEvent) and event.pull_request is not None
            )
            
            # Build prompt with appropriate context based on event type
            event_type = "PR" if is_pr else "issue"
            event_type_full = "GitHub PR" if is_pr else "GitHub issue"
            
            # Check if we have a prompt override
            if devs_options and devs_options.prompt_override:
                # Use the complete override prompt
                prompt = devs_options.prompt_override.format(
                    event_type=event_type,
                    event_type_full=event_type_full,
                    task_description=task_description,
                    repo_name=repo_name,
                    workspace_path=workspace_path,
                    github_username=self.config.github_mentioned_user
                )
            elif devs_options and devs_options.direct_commit:
                # Use direct commit prompt variant
                prompt = f"""You are an AI developer helping build a software project in a GitHub repository. 
You have been mentioned in a {event_type_full} and need to take action.

You should ensure you're on the latest commits in the repo's default branch ({devs_options.default_branch if devs_options else 'main'}). 
Commit your changes directly to the {devs_options.default_branch if devs_options else 'main'} branch unless there would be conflicts.
Only create a pull request if there would be merge conflicts when committing to {devs_options.default_branch if devs_options else 'main'}.

IMPORTANT: Do not close the issue unless the user explicitly instructs you to do so. Even if you implement a solution, leave the issue open for the user to review and close when they're satisfied.

If you need to ask for clarification, or if only asked for your thoughts, please respond with a comment on the {event_type}.

You should always comment back in any case to say what you've done (unless you are sure it wasn't intended for you). The `gh` CLI is available for GitHub operations, and you can use `git` too.

{devs_options.prompt_extra if devs_options and devs_options.prompt_extra else ''}

This is the latest update on the {event_type}, but you should just get the full thread for more details:
<latest_comment>
{task_description}
</latest_comment>

You are working in the repository `{repo_name}`.
The workspace path is `{workspace_path}`.
Your GitHub username is `{self.config.github_mentioned_user}`.

Always remember to PUSH your work to origin!
"""
            else:
                # Use the standard PR-based prompt
                # Add PR-closing instruction only for issues
                pr_closing_instruction = ""
                if not is_pr:
                    pr_closing_instruction = " (mention that it closes an issue number if it does)"
                
                # Build unified prompt with variable parts
                prompt = f"""You are an AI developer helping build a software project in a GitHub repository. 
You have been mentioned in a {event_type_full} and need to take action.

You should ensure you're on the latest commits in the repo's default branch. 
Generally work on feature branches for changes. 
Submit any changes as a pull request when done{pr_closing_instruction}.

IMPORTANT: Do not close the issue unless the user explicitly instructs you to do so. Even if you implement a solution, leave the issue open for the user to review and close when they're satisfied.

If you need to ask for clarification, or if only asked for your thoughts, please respond with a comment on the {event_type}.

You should always comment back in any case to say what you've done (unless you are sure it wasn't intended for you). The `gh` CLI is available for GitHub operations, and you can use `git` too.

{devs_options.prompt_extra if devs_options and devs_options.prompt_extra else ''}

This is the latest update on the {event_type}, but you should just get the full thread for more details:
<latest_comment>
{task_description}
</latest_comment>

You are working in the repository `{repo_name}`.
The workspace path is `{workspace_path}`.
Your GitHub username is `{self.config.github_mentioned_user}`.

Always remember to PUSH your work to origin!
"""
            
            logger.info("Built Claude prompt",
                       container=dev_name,
                       prompt_length=len(prompt),
                       event_type="PR" if is_pr else "Issue")
            
            # 4. Execute Claude (like CLI pattern) with environment variables from DEVS.yml
            logger.info("Executing Claude via ContainerManager (like CLI)",
                       container=dev_name)

            extra_env = None
            if devs_options:
                extra_env = devs_options.get_env_vars(dev_name)

            # Start container logging if enabled
            if container_log:
                container_log.start(prompt=prompt, workspace_dir=str(workspace_dir))

            success, stdout, stderr, exit_code = container_manager.exec_claude(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                prompt=prompt,
                debug=self.config.dev_mode,
                stream=False,  # Don't stream in webhook mode
                extra_env=extra_env
            )

            # Write container output to log file if enabled
            if container_log:
                container_log.write_output(stdout, stderr)
                container_log.end(
                    success=success,
                    error=stderr if not success else None
                )

            # Log full output for debugging (useful in worker logs)
            if stdout:
                logger.info("Claude stdout",
                           container=dev_name,
                           full_stdout=stdout)
            if stderr:
                logger.info("Claude stderr",
                           container=dev_name,
                           full_stderr=stderr)

            # Log error summary on failure
            if not success:
                logger.error("Claude execution failed",
                           container=dev_name,
                           stdout_tail=stdout[-1000:] if stdout and len(stdout) > 1000 else stdout,
                           stderr_tail=stderr[-1000:] if stderr and len(stderr) > 1000 else stderr,
                           success=success)

            # If failed and no stderr, check stdout for error messages
            # (Claude sometimes outputs errors to stdout)
            if not success and not stderr:
                stderr = stdout

            return success, stdout, stderr

        except Exception as e:
            error_msg = f"Claude execution failed: {str(e)}"
            logger.error("Claude execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)

            # Log the error to container log if enabled
            if container_log:
                container_log.end(success=False, error=error_msg)

            return False, "", error_msg
    
    
    async def _handle_task_completion(
        self,
        event: WebhookEvent,
        claude_output: str
    ) -> None:
        """Handle successful task completion.
        
        Args:
            event: Original webhook event
            claude_output: Output from Claude Code execution
        """
        try:
            # Skip GitHub operations for test events
            if event.is_test:
                logger.info("Skipping GitHub comment for test event", 
                           output_preview=claude_output[:100])
                return
            
            # Extract useful information from Claude's output
            #summary = self._extract_summary(claude_output)
            
            # Comment on the original issue/PR
#             comment = f"""🤖 **Claude AI Assistant Update**

# I've processed your request and taken the following actions:

# {summary}

# <details>
# <summary>Full execution log</summary>

# ```
# {claude_output[-2000:]}  # Last 2000 chars to avoid huge comments
# ```

# </details>

# This response was generated automatically by the devs webhook handler.
# """

            # Let's assume the real Claude task already added a comment somewhere
            
        except Exception as e:
            logger.error("Error handling task completion",
                        error=str(e))
    
    async def _handle_task_failure(
        self,
        event: WebhookEvent, 
        error_msg: str
    ) -> None:
        """Handle task failure.
        
        Args:
            event: Original webhook event
            error_msg: Error message
        """
        try:
            # Skip GitHub operations for test events
            if event.is_test:
                logger.info("Skipping GitHub comment for test event failure", 
                           error=error_msg)
                return
            
            log_info = ""
            if hasattr(self, '_worker_log_path') and self._worker_log_path:
                log_info = f"\n\nWorker log: `{self._worker_log_path}`"

            comment = f"""I encountered an error while trying to process your request:

```
{error_msg}
```
{log_info}
Please check the webhook handler logs for more details, or try mentioning me again with a more specific request.
"""
            
            await self._post_github_comment(event, comment)
            
        except Exception as e:
            logger.error("Error handling task failure",
                        error=str(e))
    
    async def _post_github_comment(
        self,
        event: WebhookEvent,
        comment: str
    ) -> None:
        """Post a comment to the GitHub issue/PR.
        
        Args:
            event: Webhook event
            comment: Comment text
        """
        repo_name = event.repository.full_name
        
        if isinstance(event, IssueEvent):
            await self.github_client.comment_on_issue(
                repo_name, event.issue.number, comment
            )
        elif isinstance(event, PullRequestEvent):
            await self.github_client.comment_on_pr(
                repo_name, event.pull_request.number, comment
            )
        elif isinstance(event, CommentEvent):
            if event.issue:
                await self.github_client.comment_on_issue(
                    repo_name, event.issue.number, comment
                )
            elif event.pull_request:
                await self.github_client.comment_on_pr(
                    repo_name, event.pull_request.number, comment
                )
    
    def _extract_summary(self, claude_output: str) -> str:
        """Extract a summary from Claude's output.
        
        Args:
            claude_output: Full output from Claude Code
            
        Returns:
            Extracted summary
        """
        # Simple heuristic to extract key actions
        lines = claude_output.split('\n')
        summary_lines = []
        
        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in [
                'created', 'fixed', 'implemented', 'updated', 'added',
                'pull request', 'branch', 'commit', 'merged'
            ]):
                summary_lines.append(f"- {line}")
        
        if summary_lines:
            return '\n'.join(summary_lines[:10])  # Limit to 10 items
        else:
            return "Analyzed the request and provided feedback (see full log for details)."