"""Webhook task source using FastAPI.

This module provides the webhook task source that receives GitHub webhooks
via a FastAPI HTTP endpoint and forwards them to the task processor.
"""

import asyncio
import structlog
from typing import Optional

from .base import TaskSource
from ..core.task_processor import TaskProcessor

logger = structlog.get_logger()


class WebhookTaskSource(TaskSource):
    """Task source that receives GitHub webhooks via FastAPI.

    This is the traditional webhook endpoint approach that receives
    HTTP POST requests from GitHub and processes them.
    """

    def __init__(self, task_processor: Optional[TaskProcessor] = None):
        """Initialize webhook task source.

        Args:
            task_processor: Optional task processor instance. If not provided,
                          a new one will be created.
        """
        self.task_processor = task_processor or TaskProcessor()
        self._server_task: Optional[asyncio.Task] = None
        logger.info("Webhook task source initialized")

    async def start(self) -> None:
        """Start the FastAPI webhook server.

        This method blocks until the server is stopped.
        """
        logger.info("Starting webhook task source (FastAPI)")

        # Import uvicorn here to avoid import issues
        import uvicorn
        from ..config import get_config

        config = get_config()

        # Create uvicorn config
        uvicorn_config = uvicorn.Config(
            "devs_webhook.app:app",
            host=config.webhook_host,
            port=config.webhook_port,
            log_config=None,  # Use our structlog config
        )

        # Create and start server
        server = uvicorn.Server(uvicorn_config)

        logger.info(
            "Webhook server starting",
            host=config.webhook_host,
            port=config.webhook_port,
        )

        # Run the server (blocks until stopped)
        await server.serve()

    async def stop(self) -> None:
        """Stop the webhook server."""
        logger.info("Stopping webhook task source")

        # The uvicorn server handles its own shutdown
        # We just need to cancel any running tasks

        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        logger.info("Webhook task source stopped")
