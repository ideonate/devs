"""Main webhook event handler (compatibility layer).

This module provides backward compatibility for the existing WebhookHandler API
by delegating to the new TaskProcessor.
"""

from typing import Dict, Any
import structlog

from .task_processor import TaskProcessor

logger = structlog.get_logger()


class WebhookHandler:
    """Main webhook event handler that coordinates all components.

    This is now a thin compatibility wrapper around TaskProcessor.
    """

    def __init__(self):
        """Initialize webhook handler."""
        self.task_processor = TaskProcessor()
        self.container_pool = self.task_processor.container_pool
        self.config = self.task_processor.config

        logger.info("Webhook handler initialized (compatibility mode)",
                   mentioned_user=self.config.github_mentioned_user,
                   container_pool=self.config.get_container_pool_list())
    
    async def process_webhook(
        self,
        headers: Dict[str, str],
        payload: bytes,
        delivery_id: str
    ) -> None:
        """Process a GitHub webhook event.

        Args:
            headers: HTTP headers from webhook
            payload: Raw webhook payload
            delivery_id: GitHub delivery ID for tracking
        """
        # Delegate to TaskProcessor
        await self.task_processor.process_webhook(headers, payload, delivery_id)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current handler status."""
        return await self.task_processor.get_status()

    async def stop_container(self, container_name: str) -> bool:
        """Manually stop a container."""
        return await self.task_processor.stop_container(container_name)

    async def list_containers(self) -> Dict[str, Any]:
        """List all managed containers."""
        return await self.task_processor.list_containers()
