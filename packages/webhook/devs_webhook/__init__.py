"""DevContainer Webhook Handler

A GitHub webhook handler for automated devcontainer operations with Claude Code.
"""

__version__ = "0.1.0"
__author__ = "Dan Lester"

from .config import WebhookConfig
from .core.webhook_handler import WebhookHandler
from .core.container_pool import ContainerPool
from .core.repository_manager import RepositoryManager
from .core.claude_dispatcher import ClaudeDispatcher
from .core.test_dispatcher import TestDispatcher
from .core.base_dispatcher import TaskResult

__all__ = [
    "WebhookConfig",
    "WebhookHandler",
    "ContainerPool", 
    "RepositoryManager",
    "ClaudeDispatcher",
    "TestDispatcher",
    "TaskResult",
]