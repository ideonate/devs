"""Main webhook event handler."""

import asyncio
from typing import Dict, List, Optional, Any
import structlog

from ..config import get_config
from ..github.parser import WebhookParser
from ..github.models import WebhookEvent
from .container_pool import ContainerPool
from .repository_manager import RepositoryManager
from .claude_dispatcher import ClaudeDispatcher

logger = structlog.get_logger()


class WebhookHandler:
    """Main webhook event handler that coordinates all components."""
    
    def __init__(self):
        """Initialize webhook handler."""
        self.config = get_config()
        self.container_pool = ContainerPool()
        self.repository_manager = RepositoryManager()
        self.claude_dispatcher = ClaudeDispatcher()
        
        # Track active tasks
        self.active_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("Webhook handler initialized", 
                   mentioned_user=self.config.mentioned_user,
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
            if not WebhookParser.should_process_event(event, self.config.mentioned_user):
                logger.info("Event does not contain target mentions",
                           event_type=type(event).__name__,
                           mentioned_user=self.config.mentioned_user,
                           delivery_id=delivery_id)
                return
            
            logger.info("Processing webhook event",
                       event_type=type(event).__name__,
                       repo=event.repository.full_name,
                       action=event.action,
                       delivery_id=delivery_id)
            
            # Check if we have capacity
            if len(self.active_tasks) >= self.config.max_concurrent_tasks:
                logger.warning("Maximum concurrent tasks reached, skipping",
                              active_tasks=len(self.active_tasks),
                              max_tasks=self.config.max_concurrent_tasks,
                              delivery_id=delivery_id)
                return
            
            # Process event in background task
            task = asyncio.create_task(
                self._handle_event(event, delivery_id)
            )
            self.active_tasks[delivery_id] = task
            
            # Clean up task when done
            task.add_done_callback(
                lambda t: self.active_tasks.pop(delivery_id, None)
            )
            
        except Exception as e:
            logger.error("Error processing webhook",
                        error=str(e),
                        delivery_id=delivery_id,
                        exc_info=True)
    
    async def _handle_event(self, event: WebhookEvent, delivery_id: str) -> None:
        """Handle a specific webhook event.
        
        Args:
            event: Parsed webhook event
            delivery_id: GitHub delivery ID
        """
        container_name = None
        
        try:
            # Extract task description for Claude
            task_description = WebhookParser.extract_task_description(
                event, self.config.mentioned_user
            )
            
            # Prepare repository
            repo_path = await self.repository_manager.ensure_repository(
                event.repository.full_name,
                event.repository.clone_url
            )
            
            if repo_path is None:
                logger.error("Failed to prepare repository",
                            repo=event.repository.full_name,
                            delivery_id=delivery_id)
                return
            
            # Allocate container
            container_name = await self.container_pool.allocate_container(
                event.repository.full_name,
                repo_path
            )
            
            if container_name is None:
                logger.error("No containers available",
                            repo=event.repository.full_name,
                            delivery_id=delivery_id)
                return
            
            logger.info("Container allocated",
                       container=container_name,
                       repo=event.repository.full_name,
                       delivery_id=delivery_id)
            
            # Execute task with Claude
            result = await self.claude_dispatcher.execute_task(
                container_name=container_name,
                repo_path=repo_path,
                task_description=task_description,
                event=event
            )
            
            logger.info("Task completed",
                       container=container_name,
                       repo=event.repository.full_name,
                       success=result.success,
                       delivery_id=delivery_id)
            
        except Exception as e:
            logger.error("Error handling event",
                        error=str(e),
                        container=container_name,
                        repo=event.repository.full_name,
                        delivery_id=delivery_id,
                        exc_info=True)
        
        finally:
            # Always clean up container
            if container_name:
                await self.container_pool.release_container(container_name)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current handler status."""
        container_status = await self.container_pool.get_status()
        
        return {
            "active_tasks": len(self.active_tasks),
            "max_concurrent_tasks": self.config.max_concurrent_tasks,
            "task_ids": list(self.active_tasks.keys()),
            "containers": container_status,
            "mentioned_user": self.config.mentioned_user,
        }
    
    async def stop_container(self, container_name: str) -> bool:
        """Manually stop a container."""
        return await self.container_pool.force_stop_container(container_name)
    
    async def list_containers(self) -> Dict[str, Any]:
        """List all managed containers."""
        return await self.container_pool.get_status()