"""SQS task source for receiving webhook events from AWS SQS.

This module provides the SQS task source that polls an AWS SQS queue for
webhook events and forwards them to the task processor.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any
import structlog

from .base import TaskSource
from ..core.task_processor import TaskProcessor
from ..config import get_config
from ..utils.github import verify_github_signature

logger = structlog.get_logger()


@dataclass
class BurstResult:
    """Result of a burst mode SQS run."""
    messages_processed: int
    tasks_completed: int = 0
    errors: int = 0


class SQSTaskSource(TaskSource):
    """Task source that polls AWS SQS for GitHub webhook events.

    This allows decoupling the webhook receiver (which can be a separate
    service) from the task processor. The webhook receiver puts messages
    into SQS, and this source polls them for processing.

    Expected SQS message format:
    {
        "headers": {
            "x-github-event": "issues",
            "x-github-delivery": "...",
            ...
        },
        "payload": "<base64-encoded-or-raw-json>"
    }
    """

    def __init__(
        self,
        task_processor: Optional[TaskProcessor] = None,
        burst_mode: bool = False,
        wait_for_tasks: bool = True,
        task_timeout: Optional[float] = None,
    ):
        """Initialize SQS task source.

        Args:
            task_processor: Optional task processor instance. If not provided,
                          a new one will be created.
            burst_mode: If True, process all available messages and exit instead
                       of polling indefinitely. Also disables background cleanup
                       worker (use `devs-webhook cleanup` after burst completes).
            wait_for_tasks: If True (default), burst mode will wait for all
                          queued tasks to complete before exiting. If False,
                          exits as soon as SQS queue is drained.
            task_timeout: Optional timeout in seconds for waiting on task completion
                         in burst mode. If None, waits indefinitely.
        """
        # In burst mode, disable background cleanup worker since we'll exit after processing
        # Use `devs-webhook cleanup` command after burst completes for cleanup
        enable_cleanup = not burst_mode
        self.task_processor = task_processor or TaskProcessor(enable_cleanup_worker=enable_cleanup)
        self.config = get_config()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._burst_mode = burst_mode
        self._wait_for_tasks = wait_for_tasks
        self._task_timeout = task_timeout
        self._messages_processed = 0
        self._tasks_completed = 0
        self._errors = 0

        # Import boto3 lazily to avoid requiring it for webhook-only deployments
        try:
            import boto3
            self.sqs_client = boto3.client(
                'sqs',
                region_name=self.config.aws_region
            )
        except ImportError:
            logger.error("boto3 not installed - required for SQS task source")
            raise ImportError(
                "boto3 is required for SQS task source. "
                "Install with: pip install boto3"
            )

        logger.info(
            "SQS task source initialized",
            queue_url=self.config.aws_sqs_queue_url,
            region=self.config.aws_region,
            burst_mode=self._burst_mode,
            wait_for_tasks=self._wait_for_tasks,
            task_timeout=self._task_timeout,
        )

    async def start(self) -> Optional[BurstResult]:
        """Start polling SQS for webhook events.

        This method blocks until the source is stopped.

        Returns:
            BurstResult if in burst mode, None otherwise.
        """
        logger.info("Starting SQS task source", burst_mode=self._burst_mode)
        self._running = True
        self._messages_processed = 0
        self._errors = 0

        try:
            if self._burst_mode:
                # Burst mode: process all available messages then exit
                return await self._run_burst_mode()
            else:
                # Normal mode: poll indefinitely
                while self._running:
                    await self._poll_and_process_messages()
                return None
        except asyncio.CancelledError:
            logger.info("SQS polling cancelled")
            raise
        except Exception as e:
            logger.error("SQS polling error", error=str(e), exc_info=True)
            raise
        finally:
            self._running = False

    async def _run_burst_mode(self) -> BurstResult:
        """Run in burst mode: process all available messages then exit.

        If wait_for_tasks is True (default), this will wait for all queued
        tasks to complete before returning. This ensures that Docker jobs
        (e.g., Claude executions) have finished, not just been queued.

        Returns:
            BurstResult with count of messages processed and tasks completed.
        """
        logger.info("Running in burst mode - will drain queue and exit",
                   wait_for_tasks=self._wait_for_tasks,
                   task_timeout=self._task_timeout)

        # Track if we found any messages on the first poll
        first_poll = True

        while self._running:
            # Poll for messages (with short wait time in burst mode)
            messages = await self._poll_messages_burst()

            if not messages:
                if first_poll:
                    # Queue was empty from the start
                    logger.info("Queue empty on first poll - no messages to process")
                else:
                    # We've drained the queue
                    logger.info(
                        "SQS queue drained",
                        messages_processed=self._messages_processed,
                        errors=self._errors,
                    )
                break

            first_poll = False

            # Process each message
            for message in messages:
                try:
                    await self._process_message(message)
                    self._messages_processed += 1
                except Exception as e:
                    self._errors += 1
                    logger.error(
                        "Error processing message in burst mode",
                        error=str(e),
                        exc_info=True,
                    )

        # Now wait for all queued tasks to complete (if enabled)
        if self._wait_for_tasks and self._messages_processed > 0:
            container_pool = self.task_processor.container_pool
            queued_count = container_pool.get_total_queued_tasks()

            logger.info("SQS queue drained, waiting for container tasks to complete",
                       queued_tasks=queued_count,
                       timeout=self._task_timeout)

            all_completed = await container_pool.wait_for_all_tasks_complete(
                timeout=self._task_timeout
            )

            if all_completed:
                self._tasks_completed = self._messages_processed
                logger.info("All container tasks completed successfully",
                           tasks_completed=self._tasks_completed)
            else:
                # Timeout occurred - some tasks may still be running
                remaining = container_pool.get_total_queued_tasks()
                self._tasks_completed = self._messages_processed - remaining
                logger.warning("Timeout waiting for container tasks",
                              tasks_completed=self._tasks_completed,
                              tasks_remaining=remaining)
        else:
            # Not waiting for tasks, or no messages processed
            self._tasks_completed = 0

        return BurstResult(
            messages_processed=self._messages_processed,
            tasks_completed=self._tasks_completed,
            errors=self._errors,
        )

    async def _poll_messages_burst(self) -> list:
        """Poll for messages in burst mode (short wait, multiple messages).

        Returns:
            List of SQS messages.
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sqs_client.receive_message(
                    QueueUrl=self.config.aws_sqs_queue_url,
                    MaxNumberOfMessages=10,  # Get up to 10 messages at once in burst mode
                    WaitTimeSeconds=1,  # Short wait in burst mode
                    AttributeNames=['All'],
                    MessageAttributeNames=['All']
                )
            )
            return response.get('Messages', [])
        except Exception as e:
            logger.error("Error polling SQS in burst mode", error=str(e), exc_info=True)
            return []

    async def stop(self) -> None:
        """Stop polling SQS and clean up containers."""
        logger.info("Stopping SQS task source")
        self._running = False

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # Gracefully shutdown the container pool
        logger.info("Shutting down container pool")
        try:
            await self.task_processor.container_pool.shutdown()
            logger.info("Container pool shutdown complete")
        except Exception as e:
            logger.error("Error during container pool shutdown", error=str(e))

        logger.info("SQS task source stopped")

    async def _poll_and_process_messages(self) -> None:
        """Poll SQS and process any available messages.

        This uses long polling to efficiently wait for messages.
        """
        try:
            # Run SQS receive in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sqs_client.receive_message(
                    QueueUrl=self.config.aws_sqs_queue_url,
                    MaxNumberOfMessages=1,  # Process one at a time
                    WaitTimeSeconds=self.config.sqs_wait_time_seconds,
                    AttributeNames=['All'],
                    MessageAttributeNames=['All']
                )
            )

            messages = response.get('Messages', [])

            if not messages:
                # No messages available, will poll again
                return

            for message in messages:
                await self._process_message(message)

        except Exception as e:
            logger.error("Error polling SQS", error=str(e), exc_info=True)
            # Wait a bit before retrying on error
            await asyncio.sleep(5)

    async def _process_message(self, message: Dict[str, Any]) -> None:
        """Process a single SQS message.

        Args:
            message: SQS message containing webhook event
        """
        receipt_handle = message['ReceiptHandle']
        message_id = message['MessageId']

        try:
            # Parse message body
            body = json.loads(message['Body'])

            # Extract headers and payload
            headers = body.get('headers', {})
            payload_data = body.get('payload')

            # Convert payload to bytes if needed
            if isinstance(payload_data, str):
                # Check if it's base64 encoded
                if payload_data.startswith('{') or payload_data.startswith('['):
                    # Raw JSON string
                    payload = payload_data.encode('utf-8')
                else:
                    # Assume base64 encoded
                    import base64
                    payload = base64.b64decode(payload_data)
            elif isinstance(payload_data, dict):
                # Already parsed JSON, re-encode to bytes
                payload = json.dumps(payload_data).encode('utf-8')
            else:
                payload = payload_data

            # Generate delivery ID if not present
            delivery_id = headers.get('x-github-delivery', f'sqs-{message_id}')

            # Verify GitHub webhook signature (defense in depth)
            signature = headers.get('x-hub-signature-256', '')
            if not verify_github_signature(payload, signature, self.config.github_webhook_secret):
                error_msg = "Invalid GitHub webhook signature - possible security breach or misconfiguration"
                logger.error(
                    "Invalid webhook signature from SQS message",
                    message_id=message_id,
                    delivery_id=delivery_id,
                    signature_present=bool(signature),
                )
                # Send to DLQ for investigation
                if self.config.aws_sqs_dlq_url:
                    await self._send_to_dlq(message, error_msg)
                # Delete from main queue (don't retry invalid signatures)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.sqs_client.delete_message(
                        QueueUrl=self.config.aws_sqs_queue_url,
                        ReceiptHandle=receipt_handle
                    )
                )
                logger.warning(
                    "Rejected SQS message with invalid signature",
                    message_id=message_id,
                )
                return

            logger.info(
                "Processing SQS message",
                message_id=message_id,
                delivery_id=delivery_id,
                event_type=headers.get('x-github-event', 'unknown'),
            )

            # Process the webhook event
            await self.task_processor.process_webhook(
                headers=headers,
                payload=payload,
                delivery_id=delivery_id
            )

            # Delete message from queue on success
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.sqs_client.delete_message(
                    QueueUrl=self.config.aws_sqs_queue_url,
                    ReceiptHandle=receipt_handle
                )
            )

            logger.info(
                "SQS message processed successfully",
                message_id=message_id,
                delivery_id=delivery_id,
            )

        except Exception as e:
            error_msg = f"Failed to process SQS message: {str(e)}"
            logger.error(
                "Error processing SQS message",
                message_id=message_id,
                error=error_msg,
                exc_info=True,
            )

            # Send to DLQ if configured
            if self.config.aws_sqs_dlq_url:
                await self._send_to_dlq(message, error_msg)

            # Delete message from main queue to prevent reprocessing
            # (it's already in DLQ or we've logged the error)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.sqs_client.delete_message(
                        QueueUrl=self.config.aws_sqs_queue_url,
                        ReceiptHandle=receipt_handle
                    )
                )
                logger.info(
                    "Deleted failed message from queue",
                    message_id=message_id,
                )
            except Exception as delete_error:
                logger.error(
                    "Failed to delete message after error",
                    message_id=message_id,
                    error=str(delete_error),
                )

    async def _send_to_dlq(self, message: Dict[str, Any], error_msg: str) -> None:
        """Send a failed message to the dead-letter queue.

        Args:
            message: Original SQS message
            error_msg: Error message describing the failure
        """
        try:
            message_id = message['MessageId']

            # Add error information to the message
            dlq_body = {
                'original_message': message['Body'],
                'error': error_msg,
                'failed_at': asyncio.get_event_loop().time(),
                'original_message_id': message_id,
            }

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.sqs_client.send_message(
                    QueueUrl=self.config.aws_sqs_dlq_url,
                    MessageBody=json.dumps(dlq_body)
                )
            )

            logger.info(
                "Sent failed message to DLQ",
                message_id=message_id,
                dlq_url=self.config.aws_sqs_dlq_url,
            )

        except Exception as e:
            logger.error(
                "Failed to send message to DLQ",
                message_id=message.get('MessageId', 'unknown'),
                error=str(e),
                exc_info=True,
            )
