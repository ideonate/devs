"""Webhook worker CLI command for processing tasks in isolated subprocess."""

import os
import sys
import json
import click
import structlog
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from pydantic import TypeAdapter
from devs_common.core.project import Project

from ..config import get_config
from ..core.claude_dispatcher import ClaudeDispatcher
from ..core.test_dispatcher import TestDispatcher
from ..github.models import AnyWebhookEvent
from devs_common.devs_config import DevsOptions

logger = structlog.get_logger()


@click.command()
@click.option('--task-id', required=True, help='Unique task identifier')
@click.option('--dev-name', required=True, help='Development container name')
@click.option('--repo-name', required=True, help='Repository name (owner/repo)')
@click.option('--repo-path', required=True, help='Path to repository on host')
@click.option('--task-type', default='claude', help='Task type: claude or tests (default: claude)')
@click.option('--timeout', default=3600, help='Task timeout in seconds (default: 3600)')
def worker(task_id: str, dev_name: str, repo_name: str, repo_path: str, task_type: str, timeout: int):
    """Process a single webhook task in an isolated subprocess.
    
    This command runs the complete task processing logic in a separate process to provide
    Docker safety and prevent blocking the main web server.
    
    Large payloads (task description, webhook event data, options) are read
    from stdin as JSON to avoid command-line length limitations.
    
    Expected stdin JSON format:
    {
        "task_description": "string",
        "event": {...webhook event object...},
        "devs_options": {...devs options object...} (optional)
    }
    """
    # Set environment variable to redirect console output to stderr
    os.environ['DEVS_WEBHOOK_MODE'] = '1'
    
    # Configure structured logging for subprocess to output to stderr
    import logging
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='%(message)s'
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger.info("Worker subprocess started",
                task_id=task_id,
                dev_name=dev_name,
                repo_name=repo_name,
                repo_path=repo_path,
                timeout=timeout,
                pid=os.getpid())
    
    try:
        # Read payload from stdin
        logger.info("Reading payload from stdin", task_id=task_id)
        stdin_data = sys.stdin.read()
        
        if not stdin_data:
            raise ValueError("No data provided on stdin")
        
        try:
            payload = json.loads(stdin_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON on stdin: {e}")
        
        # Extract required fields
        task_description = payload.get('task_description')
        event_data = payload.get('event')
        devs_options_data = payload.get('devs_options')
        
        # task_description is only required for claude tasks, not for tests
        if task_type == 'claude' and not task_description:
            raise ValueError("task_description required in stdin JSON for claude tasks")
        if not event_data:
            raise ValueError("event required in stdin JSON")
        
        # Parse webhook event directly from JSON - let Pydantic figure out the type!
        logger.info("Parsing webhook event from JSON", task_id=task_id)
        
        # Use TypeAdapter to handle the union type automatically
        webhook_adapter = TypeAdapter(AnyWebhookEvent)
        event = webhook_adapter.validate_python(event_data)
        
        parsed_devs_options = None
        if devs_options_data:
            logger.info("Parsing devs options from JSON", task_id=task_id)
            parsed_devs_options = DevsOptions.model_validate(devs_options_data)
        
        # Run the task processing logic (extracted from ContainerPool._process_task)
        result = _process_task_subprocess(
            task_id=task_id,
            dev_name=dev_name,
            repo_name=repo_name,
            repo_path=Path(repo_path),
            task_description=task_description,
            event=event,
            devs_options=parsed_devs_options,
            task_type=task_type
        )
        
        # Output result as JSON to stdout
        output = {
            'success': result['success'],
            'output': result.get('output', ''),
            'error': result.get('error'),
            'task_id': task_id,
            'timestamp': datetime.now(tz=timezone.utc).isoformat()
        }
        
        print(json.dumps(output))
        sys.exit(0 if result['success'] else 1)
        
    except Exception as e:
        error_msg = f"Worker subprocess failed: {str(e)}"
        logger.error("Worker subprocess error",
                    task_id=task_id,
                    error=error_msg,
                    exc_info=True)
        
        # Output error as JSON to stdout
        error_output = {
            'success': False,
            'output': '',
            'error': error_msg,
            'task_id': task_id,
            'timestamp': datetime.now(tz=timezone.utc).isoformat()
        }
        
        print(json.dumps(error_output))
        sys.exit(1)


def _process_task_subprocess(
    task_id: str,
    dev_name: str, 
    repo_name: str,
    repo_path: Path,
    task_description: Optional[str],
    event,
    devs_options,
    task_type: str = 'claude'
) -> dict:
    """Process a single task in subprocess (extracted from ContainerPool._process_task).
    
    Args:
        task_id: Unique task identifier
        dev_name: Name of container to execute in
        repo_name: Repository name (owner/repo)
        repo_path: Path to repository on host
        task_description: Task description for Claude (unused for tests, can be None for test tasks)
        event: WebhookEvent instance
        devs_options: DevsOptions instance
        task_type: Task type ('claude' or 'tests')
        
    Returns:
        Dict with 'success', 'output', and optionally 'error' keys
    """
    logger.info("Starting task processing in subprocess",
               task_id=task_id,
               dev_name=dev_name,
               repo_name=repo_name,
               repo_path=str(repo_path),
               task_type=task_type)
    
    try:
        # Verify repository exists (should already be cloned by container_pool)
        if not repo_path.exists():
            raise Exception(f"Repository path does not exist: {repo_path}")
        
        # Create project instance
        logger.info("Creating project instance",
                   task_id=task_id,
                   dev_name=dev_name,
                   repo_path=str(repo_path),
                   task_type=task_type)
        
        project = Project(repo_path)
        workspace_name = project.get_workspace_name(dev_name)
        
        logger.info("Project created successfully",
                   task_id=task_id,
                   dev_name=dev_name,
                   project_name=project.info.name,
                   workspace_name=workspace_name,
                   task_type=task_type)
        
        # Initialize appropriate dispatcher based on task type
        if task_type == 'tests':
            dispatcher = TestDispatcher()
        else:
            # Default to Claude execution
            dispatcher = ClaudeDispatcher()
            
            # Ensure task_description is provided for Claude tasks
            if not task_description:
                raise ValueError("task_description is required for Claude tasks")
        
        logger.info(f"Executing task with {dispatcher.dispatcher_name} dispatcher",
                   task_id=task_id,
                   dev_name=dev_name,
                   workspace_name=workspace_name)
        
        result = asyncio.run(dispatcher.execute_task(
            dev_name=dev_name,
            repo_path=repo_path,
            event=event,
            devs_options=devs_options,
            task_description=task_description
        ))
        
        if result.success:
            logger.info("Task execution completed successfully",
                       task_id=task_id,
                       dev_name=dev_name,
                       output_length=len(result.output) if result.output else 0)
            
            return {
                'success': True,
                'output': result.output,
            }
        else:
            logger.error("Task execution failed",
                        task_id=task_id,
                        dev_name=dev_name,
                        error=result.error,
                        output_preview=result.output[:500] if result.output else "")
            
            return {
                'success': False,
                'output': result.output or '',
                'error': result.error
            }
            
    except Exception as e:
        error_msg = f"Task processing failed: {str(e)}"
        logger.error("Task processing error in subprocess",
                    task_id=task_id,
                    dev_name=dev_name,
                    repo_name=repo_name,
                    repo_path=str(repo_path),
                    error=error_msg,
                    error_type=type(e).__name__,
                    exc_info=True)
        
        return {
            'success': False,
            'output': '',
            'error': error_msg
        }


if __name__ == '__main__':
    import os
    worker()