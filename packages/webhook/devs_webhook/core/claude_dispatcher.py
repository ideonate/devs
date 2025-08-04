"""Claude Code CLI integration for executing tasks in containers."""

import asyncio
import shlex
import re
from typing import NamedTuple, Optional
import structlog
from pathlib import Path

from devs_common.core.project import Project
from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from ..config import get_config
from ..github.models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent, DevsOptions
from ..github.client import GitHubClient

logger = structlog.get_logger()


class TaskResult(NamedTuple):
    """Result of a Claude Code task execution."""
    success: bool
    output: str
    error: Optional[str] = None


class ClaudeDispatcher:
    """Dispatches tasks to Claude Code CLI running in containers."""
    
    def __init__(self):
        """Initialize Claude dispatcher."""
        self.config = get_config()
        self.github_client = GitHubClient(self.config.github_token)
        
        logger.info("Claude dispatcher initialized")
    
    async def execute_task(
        self,
        dev_name: str,
        workspace_dir: Path,
        repo_path: Path,
        task_description: str,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None
    ) -> TaskResult:
        """Execute a task using Claude Code CLI in a container.
        
        Args:
            dev_name: Name of dev container (e.g., eamonn)
            workspace_dir: Workspace directory path on host
            repo_path: Path to repository on host (already calculated by container_pool)
            task_description: Task description for Claude
            event: Original webhook event
            devs_options: Options from DEVS.yml file
            
        Returns:
            Task execution result
        """
        try:
            logger.info("Starting Claude Code CLI task",
                       container=dev_name,
                       repo=event.repository.full_name,
                       workspace_dir=str(workspace_dir),
                       repo_path=str(repo_path))
            
            # Build Claude Code prompt with context
            prompt = self._build_claude_prompt(task_description, workspace_dir, event, devs_options)

            # Use ContainerManager like CLI does - repo_path provided by container_pool
            result = await self._execute_claude_via_container_manager(dev_name, workspace_dir, prompt, repo_path, event)
            
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
            return TaskResult(success=False, output="", error=error_msg)
    
    async def _execute_claude_via_container_manager(
        self,
        dev_name: str,
        workspace_dir: Path,
        prompt: str,
        repo_path: Path,
        event: WebhookEvent
    ) -> TaskResult:
        """Execute Claude Code CLI using ContainerManager (same as CLI shell command).
        
        Args:
            dev_name: Name of dev container (e.g., eamonn)
            workspace_dir: Workspace directory path on host
            prompt: Claude Code prompt to execute
            repo_path: Path to the repository on the host
            event: Original webhook event
            
        Returns:
            Task execution result
        """
        try:
            # Use the same infrastructure as CLI - create project and container manager
            project = Project(repo_path)
            container_manager = ContainerManager(project, self.config)
            
            logger.info("Using ContainerManager to execute Claude",
                       container=dev_name,
                       workspace_dir=str(workspace_dir),
                       prompt_length=len(prompt) if not event.is_test else 0)

            if event.is_test:
                # For test events, just return success
                logger.info("Test event - skipping Claude execution")
                return TaskResult(success=True, output="Test event received, no execution", error=None)
            
            # Execute Claude using ContainerManager - same as CLI does
            success, output, error = container_manager.exec_claude(
                dev_name, 
                workspace_dir, 
                prompt, 
                debug=self.config.dev_mode
            )
            
            if success:
                logger.info("Claude CLI execution completed via ContainerManager",
                           container=dev_name,
                           output_length=len(output),
                           output_preview=output[:200] + "..." if len(output) > 200 else output)
            else:
                logger.error("Claude CLI execution failed via ContainerManager",
                           container=dev_name,
                           error_length=len(error),
                           error_preview=error[:500] + "..." if len(error) > 500 else error,
                           output_length=len(output),
                           full_error=error)
            
            return TaskResult(
                success=success,
                output=output,
                error=error if not success else None
            )
            
        except Exception as e:
            error_msg = f"ContainerManager execution failed: {str(e)}"
            logger.error("ContainerManager execution error",
                        container=dev_name,
                        error=error_msg,
                        exc_info=True)
            return TaskResult(success=False, output="", error=error_msg)
    
    def _build_claude_prompt(
        self,
        task_description: str,
        workspace_dir: Path,
        event: WebhookEvent,
        devs_options: Optional[DevsOptions] = None
    ) -> str:
        """Build the complete prompt for Claude Code CLI.
        
        Args:
            task_description: Base task description
            workspace_dir: Workspace directory path on host  
            event: Webhook event
            devs_options: Options from DEVS.yml file
            
        Returns:
            Complete prompt for Claude Code CLI
        """
        repo_name = event.repository.full_name
        # Get workspace name from directory name
        workspace_name = workspace_dir.name
        workspace_path = f"/workspaces/{workspace_name}"
        
        prompt = f"""You are an AI developer helping build a software project in a GitHub repository. 
You have been mentioned in a GitHub issue/PR and need to take action.

You should ensure you're on the latest commits in the repo's default branch. 
Generally work on feature branches for changes. 
Submit any changes as a pull request when done (mention that it closes an issue number if it does).

If you need to ask for clarification, or if only asked for your thoughts, please respond with a comment on the issue/PR.

You should always comment back in any case to say what you've done. The `gh` CLI is available for GitHub operations, and you can use `git` too.

{devs_options.prompt_extra}

This is the latest update on the issue/PR, but you should just get the full thread for more details:
<latest_comment>
{task_description}
</latest_comment>

You are working in the repository `{repo_name}`.
The workspace path is `{workspace_path}`.
Your GitHub username is `{self.config.github_mentioned_user}`.
"""
        
        # Append any extra prompt instructions from DEVS.yml
        if devs_options and devs_options.prompt_extra:
            prompt += f"\n{devs_options.prompt_extra}\n"
        
        return prompt
    
    def _sanitize_outgoing_comment(self, comment: str, mentioned_user: str) -> str:
        """Sanitize outgoing comment to prevent feedback loops.
        
        Args:
            comment: The comment text to sanitize
            mentioned_user: The bot username to remove mentions of
            
        Returns:
            Sanitized comment text
        """
        # Replace @mention with just the username to prevent loops
        # Use negative lookbehind to avoid replacing @@mentions (which are already escaped)
        pattern = re.compile(rf"(?<!@)@{re.escape(mentioned_user)}\b", re.IGNORECASE)
        sanitized = pattern.sub(mentioned_user, comment)
        
        # Log if we made any changes
        if sanitized != comment:
            logger.info("Sanitized outgoing comment to prevent feedback loop",
                       original_length=len(comment),
                       sanitized_length=len(sanitized),
                       mentioned_user=mentioned_user)
        
        return sanitized
    
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
            
            # Sanitize output to prevent feedback loops
            sanitized_output = self._sanitize_outgoing_comment(claude_output, self.config.github_mentioned_user)
            await self._post_github_comment(event, sanitized_output)
            
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
            
            comment = f"""I encountered an error while trying to process your request:

```
{error_msg}
```

Please check the webhook handler logs for more details, or try mentioning me again with a more specific request.
"""
            
            # Sanitize comment to prevent feedback loops
            sanitized_comment = self._sanitize_outgoing_comment(comment, self.config.github_mentioned_user)
            await self._post_github_comment(event, sanitized_comment)
            
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