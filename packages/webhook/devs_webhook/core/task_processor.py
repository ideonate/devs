"""Core task processor that handles webhook event processing.

This module provides the TaskProcessor class which is decoupled from the task source
(webhook, SQS, etc.) and handles all the business logic of processing GitHub events.
"""

from typing import Dict, Any
import structlog

from ..config import get_config
from ..github.parser import WebhookParser
from ..github.client import GitHubClient
from ..github.models import IssueEvent, PullRequestEvent, CommentEvent
from .container_pool import ContainerPool
from .deduplication import is_duplicate_content, get_cache_stats

logger = structlog.get_logger()


class TaskProcessor:
    """Core task processor that handles webhook event processing.

    This class is decoupled from the task source (webhook endpoint, SQS, etc.)
    and contains all the business logic for processing GitHub webhook events.
    """

    def __init__(self, container_pool: ContainerPool = None, enable_cleanup_worker: bool = True):
        """Initialize task processor.

        Args:
            container_pool: Optional container pool instance. If not provided,
                          a new one will be created.
            enable_cleanup_worker: If True (default), enables background cleanup
                of idle containers. Set to False for burst mode.
        """
        self.config = get_config()
        self.container_pool = container_pool or ContainerPool(enable_cleanup_worker=enable_cleanup_worker)
        self.github_client = GitHubClient(self.config)

        logger.info("Task processor initialized",
                   mentioned_user=self.config.github_mentioned_user,
                   container_pool=self.config.get_container_pool_list(),
                   cleanup_worker=enable_cleanup_worker)

    async def _add_eyes_reaction(self, event: Any, repo_name: str) -> None:
        """Add an eyes reaction to indicate we're processing the event.

        Args:
            event: The webhook event object
            repo_name: Repository in format "owner/repo"
        """
        try:
            reaction_added = False

            # Determine what to react to based on event type
            if isinstance(event, CommentEvent):
                # React to the comment itself
                reaction_added = await self.github_client.add_reaction_to_comment(
                    repo=repo_name,
                    comment_id=event.comment.id,
                    reaction="eyes"
                )
                logger.info("Attempting to add reaction to comment",
                           comment_id=event.comment.id,
                           repo=repo_name)
            elif isinstance(event, IssueEvent):
                # React to the issue
                reaction_added = await self.github_client.add_reaction_to_issue(
                    repo=repo_name,
                    issue_number=event.issue.number,
                    reaction="eyes"
                )
                logger.info("Attempting to add reaction to issue",
                           issue_number=event.issue.number,
                           repo=repo_name)
            elif isinstance(event, PullRequestEvent):
                # React to the PR (PRs are issues in GitHub API)
                reaction_added = await self.github_client.add_reaction_to_pr(
                    repo=repo_name,
                    pr_number=event.pull_request.number,
                    reaction="eyes"
                )
                logger.info("Attempting to add reaction to PR",
                           pr_number=event.pull_request.number,
                           repo=repo_name)

            if reaction_added:
                logger.info("Successfully added eyes reaction",
                           event_type=type(event).__name__,
                           repo=repo_name)
            else:
                logger.warning("Could not add eyes reaction",
                              event_type=type(event).__name__,
                              repo=repo_name)

        except Exception as e:
            # Log the error but don't fail the webhook processing
            logger.error("Error adding reaction to event - continuing anyway",
                        error=str(e),
                        event_type=type(event).__name__,
                        repo=repo_name,
                        exc_info=True)

    async def process_webhook(
        self,
        headers: Dict[str, str],
        payload: bytes,
        delivery_id: str
    ) -> None:
        """Process a GitHub webhook event.

        This is the main entry point for processing webhook events, regardless
        of the source (FastAPI endpoint, SQS, etc.).

        Args:
            headers: HTTP headers from webhook
            payload: Raw webhook payload
            delivery_id: Unique delivery ID for tracking
        """
        try:
            # Parse webhook event
            event = WebhookParser.parse_webhook(headers, payload)

            if event is None:
                logger.info("Unsupported webhook event type",
                           event_type=headers.get("x-github-event"),
                           delivery_id=delivery_id)
                return

            # Get trigger user for authorization checks (done per-dispatch-type below)
            trigger_user = event.sender.login

            # Check if repository is allowed
            repo_owner = event.repository.owner.login
            if not self.config.is_repository_allowed(event.repository.full_name, repo_owner):
                logger.warning("Repository not in allowlist - rejecting webhook",
                              repo=event.repository.full_name,
                              owner=repo_owner,
                              delivery_id=delivery_id,
                              event_type=type(event).__name__)
                return

            # Load repository configuration to check for CI mode
            devs_options = await self.container_pool.ensure_repo_config(event.repository.full_name)

            # Check if we should process this event for CI
            process_for_ci = WebhookParser.should_process_event_for_ci(event, devs_options)

            # Check if we should process this event for mentions
            process_for_mentions = WebhookParser.should_process_event(event, self.config.github_mentioned_user)

            # Skip if neither CI nor mentions apply
            if not process_for_ci and not process_for_mentions:
                logger.info("Event does not trigger CI or contain target mentions",
                           event_type=type(event).__name__,
                           mentioned_user=self.config.github_mentioned_user,
                           ci_enabled=devs_options.ci_enabled if devs_options else False,
                           delivery_id=delivery_id)
                return

            logger.info("Event processing mode determined",
                       event_type=type(event).__name__,
                       process_for_ci=process_for_ci,
                       process_for_mentions=process_for_mentions,
                       delivery_id=delivery_id)

            # Check for duplicate content
            content_hash = event.get_content_hash()
            if content_hash:
                event_description = f"{type(event).__name__}({event.action}) {event.repository.full_name}"
                if hasattr(event, 'issue'):
                    event_description += f" issue#{event.issue.number}"
                elif hasattr(event, 'pull_request'):
                    event_description += f" pr#{event.pull_request.number}"

                if is_duplicate_content(content_hash, event_description):
                    logger.info("Duplicate content detected, skipping processing",
                               event_type=type(event).__name__,
                               action=event.action,
                               content_hash=content_hash,
                               event_description=event_description,
                               delivery_id=delivery_id)
                    return

            logger.info("Processing webhook event",
                       event_type=type(event).__name__,
                       repo=event.repository.full_name,
                       action=event.action,
                       delivery_id=delivery_id)

            tasks_queued = []

            # Queue CI task if applicable (with separate CI authorization check)
            if process_for_ci:
                if not self.config.is_user_authorized_for_ci(trigger_user):
                    logger.warning("User not authorized to trigger CI dispatch",
                                  user=trigger_user,
                                  repo=event.repository.full_name,
                                  delivery_id=delivery_id,
                                  event_type=type(event).__name__)
                else:
                    ci_task_id = f"{delivery_id}-ci"
                    ci_success = await self.container_pool.queue_task(
                        task_id=ci_task_id,
                        repo_name=event.repository.full_name,
                        task_description="",  # Not used for CI tasks
                        event=event,
                        task_type='tests'
                    )

                    if ci_success:
                        tasks_queued.append("CI tests")
                        logger.info("CI task queued successfully",
                                   delivery_id=ci_task_id,
                                   repo=event.repository.full_name)
                    else:
                        logger.error("Failed to queue CI task",
                                    delivery_id=ci_task_id,
                                    repo=event.repository.full_name)

            # Queue mention-based task if applicable (with Claude authorization check)
            if process_for_mentions:
                if not self.config.is_user_authorized_to_trigger(trigger_user):
                    logger.warning("User not authorized to trigger Claude dispatch",
                                  user=trigger_user,
                                  repo=event.repository.full_name,
                                  delivery_id=delivery_id,
                                  event_type=type(event).__name__)
                else:
                    # Get context from the event for Claude
                    task_description = event.get_context_for_claude()

                    mention_task_id = f"{delivery_id}-claude" if process_for_ci else delivery_id
                    mention_success = await self.container_pool.queue_task(
                        task_id=mention_task_id,
                        repo_name=event.repository.full_name,
                        task_description=task_description,
                        event=event,
                        task_type='claude'
                    )

                    if mention_success:
                        tasks_queued.append("Claude processing")
                        logger.info("Claude task queued successfully",
                                   delivery_id=mention_task_id,
                                   repo=event.repository.full_name)

                        # Try to add "eyes" reaction to indicate we're looking into it
                        await self._add_eyes_reaction(event, event.repository.full_name)
                    else:
                        logger.error("Failed to queue Claude task",
                                    delivery_id=mention_task_id,
                                    repo=event.repository.full_name)

            if tasks_queued:
                logger.info("Tasks queued successfully",
                           delivery_id=delivery_id,
                           repo=event.repository.full_name,
                           tasks=tasks_queued)
            else:
                logger.error("Failed to queue any tasks",
                            delivery_id=delivery_id,
                            repo=event.repository.full_name)

        except Exception as e:
            logger.error("Error processing webhook",
                        error=str(e),
                        delivery_id=delivery_id,
                        exc_info=True)

    async def get_status(self) -> Dict[str, Any]:
        """Get current processor status."""
        container_status = await self.container_pool.get_status()

        # Calculate total queued tasks across all containers
        total_queued = sum(
            self.container_pool.container_queues[container].qsize()
            for container in self.config.get_container_pool_list()
        )

        return {
            "queued_tasks": total_queued,
            "container_pool_size": len(self.config.get_container_pool_list()),
            "containers": container_status,
            "mentioned_user": self.config.github_mentioned_user,
            "authorized_trigger_users": self.config.get_authorized_trigger_users_list(),
            "authorized_ci_trigger_users": self.config.get_authorized_ci_trigger_users_list(),
            "deduplication_cache": get_cache_stats(),
        }

    async def stop_container(self, container_name: str) -> bool:
        """Manually stop a container."""
        return await self.container_pool.force_stop_container(container_name)

    async def list_containers(self) -> Dict[str, Any]:
        """List all managed containers."""
        return await self.container_pool.get_status()
