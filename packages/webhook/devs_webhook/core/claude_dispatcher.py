"""Claude Code SDK integration for executing tasks."""

import asyncio
import subprocess
import os
from pathlib import Path
from typing import NamedTuple, Optional
import structlog

from claude_code_sdk import query, ClaudeCodeOptions

from ..config import get_config
from ..github.models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent
from ..github.client import GitHubClient

logger = structlog.get_logger()


class TaskResult(NamedTuple):
    """Result of a Claude Code task execution."""
    success: bool
    output: str
    error: Optional[str] = None


class ClaudeDispatcher:
    """Dispatches tasks to Claude Code SDK for execution."""
    
    def __init__(self):
        """Initialize Claude dispatcher."""
        self.config = get_config()
        self.github_client = GitHubClient(self.config.github_token)
        
        logger.info("Claude dispatcher initialized",
                   model=self.config.claude_model)
    
    async def execute_task(
        self,
        container_name: str,
        repo_path: Path,
        task_description: str,
        event: WebhookEvent
    ) -> TaskResult:
        """Execute a task using Claude Code SDK.
        
        Args:
            container_name: Name of container to execute in
            repo_path: Path to repository
            task_description: Task description for Claude
            event: Original webhook event
            
        Returns:
            Task execution result
        """
        try:
            logger.info("Starting Claude Code task",
                       container=container_name,
                       repo=event.repository.full_name)
            
            # Prepare environment for Claude Code
            workspace_dir = self.config.workspace_dir / f"{repo_path.name}-{container_name}"
            
            # Build Claude Code prompt with context
            prompt = self._build_claude_prompt(
                task_description, workspace_dir, event
            )
            
            # Execute Claude Code task
            output_lines = []
            try:
                async for message in query(
                    prompt=prompt,
                    options=ClaudeCodeOptions(
                        max_turns=10,  # Allow multi-turn conversation
                        model=self.config.claude_model,
                    )
                ):
                    output_lines.append(str(message))
                    logger.debug("Claude Code output", message=str(message))
                
                full_output = "\n".join(output_lines)
                
                # Post-process results
                await self._handle_task_completion(event, full_output)
                
                return TaskResult(success=True, output=full_output)
                
            except Exception as e:
                error_msg = f"Claude Code execution failed: {str(e)}"
                logger.error("Claude Code task failed",
                           container=container_name,
                           error=error_msg)
                
                # Try to comment on GitHub about the failure
                await self._handle_task_failure(event, error_msg)
                
                return TaskResult(success=False, output="", error=error_msg)
                
        except Exception as e:
            error_msg = f"Task setup failed: {str(e)}"
            logger.error("Task execution setup failed",
                        container=container_name,
                        error=error_msg)
            return TaskResult(success=False, output="", error=error_msg)
    
    def _build_claude_prompt(
        self,
        task_description: str,
        workspace_dir: Path,
        event: WebhookEvent
    ) -> str:
        """Build the complete prompt for Claude Code.
        
        Args:
            task_description: Base task description
            workspace_dir: Workspace directory path
            event: Webhook event
            
        Returns:
            Complete prompt for Claude Code
        """
        repo_name = event.repository.full_name
        
        prompt = f"""You are an AI assistant helping with GitHub repository tasks. You have been mentioned in a GitHub issue/PR and need to take action.

{task_description}

IMPORTANT SETUP INSTRUCTIONS:
1. First, navigate to the workspace directory: cd {workspace_dir}
2. Set up Git configuration if needed:
   git config --global user.name "Claude AI Assistant"
   git config --global user.email "claude@anthropic.com"
3. Ensure you're on the latest main/master branch: git pull origin main || git pull origin master

AVAILABLE TOOLS:
- `gh` CLI for GitHub operations (already authenticated)
- `git` for version control operations
- Standard Unix tools and development environment
- The repository is already cloned in your current workspace

WORKFLOW GUIDELINES:
- Always start by understanding the current codebase structure
- Read relevant files to understand the context
- If making changes, create a feature branch: git checkout -b claude/fix-issue-[number]
- Make targeted, well-tested changes
- Write clear commit messages
- Push your branch and create a PR if appropriate
- Always comment back on the original issue/PR with your findings

GitHub Repository: {repo_name}
Workspace Location: {workspace_dir}

Please proceed with analyzing and addressing this request step by step.
"""
        
        return prompt
    
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
            # Extract useful information from Claude's output
            summary = self._extract_summary(claude_output)
            
            # Comment on the original issue/PR
            comment = f"""🤖 **Claude AI Assistant Update**

I've processed your request and taken the following actions:

{summary}

<details>
<summary>Full execution log</summary>

```
{claude_output[-2000:]}  # Last 2000 chars to avoid huge comments
```

</details>

This response was generated automatically by the devs webhook handler.
"""
            
            await self._post_github_comment(event, comment)
            
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
            comment = f"""🤖 **Claude AI Assistant Error**

I encountered an error while trying to process your request:

```
{error_msg}
```

Please check the webhook handler logs for more details, or try mentioning me again with a more specific request.

This response was generated automatically by the devs webhook handler.
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