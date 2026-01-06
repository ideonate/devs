"""Base dispatcher class with shared functionality."""

from typing import NamedTuple, Optional
import structlog
from pathlib import Path

from ..config import get_config
from ..github.models import WebhookEvent
from ..github.client import GitHubClient
from devs_common.devs_config import DevsOptions

logger = structlog.get_logger()


class TaskResult(NamedTuple):
    """Result of a task execution (consolidates TestResult and TaskResult)."""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None


class BaseDispatcher:
    """Base class for dispatchers with common functionality."""
    
    def __init__(self, dispatcher_type: str = "base"):
        """Initialize dispatcher with common setup.
        
        Args:
            dispatcher_type: Type of dispatcher for logging
        """
        self.config = get_config()
        self.github_client = GitHubClient(self.config)
        
        logger.info(f"{dispatcher_type.title()} dispatcher initialized")
    
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
        """Execute operation in container - to be implemented by subclasses.

        Args:
            dev_name: Name of dev container (e.g., eamonn)
            repo_path: Path to repository on host
            event: Original webhook event
            devs_options: Options from DEVS.yml file
            task_description: Task description
            task_id: Optional task identifier for logging
            worker_log_path: Optional path to worker log file (for including in failure messages)

        Returns:
            Task execution result
        """
        raise NotImplementedError("Subclasses must implement execute_task")