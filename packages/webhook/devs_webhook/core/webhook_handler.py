"""Main webhook event handler."""

from typing import Dict, Any
import structlog

from ..config import get_config
from ..github.parser import WebhookParser
from .container_pool import ContainerPool

logger = structlog.get_logger()


class WebhookHandler:
    """Main webhook event handler that coordinates all components."""
    
    def __init__(self):
        """Initialize webhook handler."""
        self.config = get_config()
        self.container_pool = ContainerPool()
        
        logger.info("Webhook handler initialized", 
                   mentioned_user=self.config.github_mentioned_user,
                   container_pool=self.config.container_pool)
    
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
        try:
            # Parse webhook event
            event = WebhookParser.parse_webhook(headers, payload)
            
            if event is None:
                logger.info("Unsupported webhook event type", 
                           event_type=headers.get("x-github-event"),
                           delivery_id=delivery_id)
                return
            
            # Check if we should process this event
            if not WebhookParser.should_process_event(event, self.config.github_mentioned_user):
                logger.info("Event does not contain target mentions",
                           event_type=type(event).__name__,
                           mentioned_user=self.config.github_mentioned_user,
                           delivery_id=delivery_id)
                return
            
            logger.info("Processing webhook event",
                       event_type=type(event).__name__,
                       repo=event.repository.full_name,
                       action=event.action,
                       delivery_id=delivery_id)
            
            # Get context from the event for Claude
            task_description = event.get_context_for_claude()
            
            # Queue the task in the container pool
            success = await self.container_pool.queue_task(
                task_id=delivery_id,
                repo_name=event.repository.full_name,
                task_description=task_description,
                event=event
            )
            
            if success:
                logger.info("Task queued successfully",
                           delivery_id=delivery_id,
                           repo=event.repository.full_name)
            else:
                logger.error("Failed to queue task",
                            delivery_id=delivery_id,
                            repo=event.repository.full_name)
            
        except Exception as e:
            logger.error("Error processing webhook",
                        error=str(e),
                        delivery_id=delivery_id,
                        exc_info=True)
    
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current handler status."""
        container_status = await self.container_pool.get_status()
        
        # Calculate total queued tasks across all containers
        total_queued = sum(
            self.container_pool.container_queues[container].qsize()
            for container in self.config.container_pool
        )
        
        return {
            "queued_tasks": total_queued,
            "container_pool_size": len(self.config.container_pool),
            "containers": container_status,
            "mentioned_user": self.config.github_mentioned_user,
        }
    
    async def stop_container(self, container_name: str) -> bool:
        """Manually stop a container."""
        return await self.container_pool.force_stop_container(container_name)
    
    async def list_containers(self) -> Dict[str, Any]:
        """List all managed containers."""
        return await self.container_pool.get_status()