"""Tests for SQS burst mode functionality."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from devs_webhook.sources.sqs_source import SQSTaskSource, BurstResult


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.aws_sqs_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
    config.aws_sqs_dlq_url = ""
    config.aws_region = "us-east-1"
    config.sqs_wait_time_seconds = 20
    config.github_webhook_secret = "test-secret"
    return config


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    return MagicMock()


@pytest.fixture
def mock_task_processor():
    """Create a mock task processor with properly mocked container_pool."""
    processor = MagicMock()
    processor.process_webhook = AsyncMock()

    # Mock the container_pool with async methods
    mock_pool = MagicMock()
    mock_pool.get_total_queued_tasks = MagicMock(return_value=0)
    mock_pool.wait_for_all_tasks_complete = AsyncMock(return_value=True)
    processor.container_pool = mock_pool

    return processor


def create_sqs_message(message_id: str, body: dict) -> dict:
    """Create a mock SQS message."""
    return {
        "MessageId": message_id,
        "ReceiptHandle": f"receipt-{message_id}",
        "Body": json.dumps(body),
    }


class TestBurstResult:
    """Tests for BurstResult dataclass."""

    def test_burst_result_creation(self):
        """Test creating a BurstResult."""
        result = BurstResult(messages_processed=5, tasks_completed=4, errors=1)
        assert result.messages_processed == 5
        assert result.tasks_completed == 4
        assert result.errors == 1

    def test_burst_result_defaults(self):
        """Test BurstResult with default errors."""
        result = BurstResult(messages_processed=3)
        assert result.messages_processed == 3
        assert result.tasks_completed == 0
        assert result.errors == 0


class TestSQSBurstMode:
    """Tests for SQS burst mode."""

    @pytest.mark.asyncio
    async def test_burst_mode_empty_queue_returns_zero_messages(self, mock_config, mock_task_processor):
        """Test that burst mode returns zero messages when queue is empty."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()
                mock_sqs.receive_message.return_value = {"Messages": []}
                mock_boto.return_value = mock_sqs

                source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                result = await source.start()

                assert result is not None
                assert result.messages_processed == 0
                assert result.errors == 0

    @pytest.mark.asyncio
    async def test_burst_mode_processes_single_message(self, mock_config, mock_task_processor):
        """Test burst mode processes a single message and exits."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                # First call returns one message, second returns empty (drained)
                message = create_sqs_message("msg-1", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": "test-delivery"},
                    "payload": {"action": "opened"}
                })
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [message]},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                # Mock signature verification
                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                    result = await source.start()

                assert result is not None
                assert result.messages_processed == 1
                assert result.errors == 0

                # Verify message was deleted
                assert mock_sqs.delete_message.call_count == 1

    @pytest.mark.asyncio
    async def test_burst_mode_processes_multiple_messages(self, mock_config, mock_task_processor):
        """Test burst mode processes multiple messages and exits."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                # Create multiple messages
                messages = [
                    create_sqs_message(f"msg-{i}", {
                        "headers": {"x-github-event": "issues", "x-github-delivery": f"delivery-{i}"},
                        "payload": {"action": "opened"}
                    })
                    for i in range(5)
                ]

                # First call returns 5 messages, second returns empty
                mock_sqs.receive_message.side_effect = [
                    {"Messages": messages},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                    result = await source.start()

                assert result is not None
                assert result.messages_processed == 5
                assert result.errors == 0

                # Verify all messages were deleted
                assert mock_sqs.delete_message.call_count == 5

    @pytest.mark.asyncio
    async def test_burst_mode_drains_queue_with_multiple_polls(self, mock_config, mock_task_processor):
        """Test burst mode continues polling until queue is empty."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                # Multiple batches of messages
                batch1 = [create_sqs_message(f"msg-1-{i}", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": f"delivery-1-{i}"},
                    "payload": {"action": "opened"}
                }) for i in range(3)]

                batch2 = [create_sqs_message(f"msg-2-{i}", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": f"delivery-2-{i}"},
                    "payload": {"action": "opened"}
                }) for i in range(2)]

                mock_sqs.receive_message.side_effect = [
                    {"Messages": batch1},
                    {"Messages": batch2},
                    {"Messages": []},  # Queue drained
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                    result = await source.start()

                assert result is not None
                assert result.messages_processed == 5  # 3 + 2
                assert result.errors == 0

    @pytest.mark.asyncio
    async def test_burst_mode_continues_on_processing_errors(self, mock_config, mock_task_processor):
        """Test burst mode continues processing even if individual messages fail.

        Note: Errors inside _process_message are caught internally (and messages
        are sent to DLQ if configured). The burst mode counter counts all
        messages that were processed, regardless of whether the underlying
        task_processor succeeded.
        """
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                messages = [
                    create_sqs_message("msg-1", {
                        "headers": {"x-github-event": "issues", "x-github-delivery": "delivery-1"},
                        "payload": {"action": "opened"}
                    }),
                    create_sqs_message("msg-2", {
                        "headers": {"x-github-event": "issues", "x-github-delivery": "delivery-2"},
                        "payload": {"action": "opened"}
                    }),
                ]

                mock_sqs.receive_message.side_effect = [
                    {"Messages": messages},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                # Make the task processor fail on first message
                mock_task_processor.process_webhook.side_effect = [
                    Exception("Processing failed"),
                    None,  # Second succeeds
                ]

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                    result = await source.start()

                assert result is not None
                # Both messages were processed (error was caught inside _process_message)
                assert result.messages_processed == 2
                # Delete was called for both messages
                assert mock_sqs.delete_message.call_count == 2

    @pytest.mark.asyncio
    async def test_non_burst_mode_returns_none(self, mock_config, mock_task_processor):
        """Test that non-burst mode returns None (would run indefinitely)."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()
                mock_sqs.receive_message.return_value = {"Messages": []}
                mock_boto.return_value = mock_sqs

                source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=False)

                # Stop immediately to avoid infinite loop
                async def stop_after_start():
                    await asyncio.sleep(0.1)
                    source._running = False

                # Run both concurrently
                result, _ = await asyncio.gather(
                    source.start(),
                    stop_after_start(),
                )

                assert result is None

    @pytest.mark.asyncio
    async def test_burst_mode_uses_short_wait_time(self, mock_config, mock_task_processor):
        """Test burst mode uses short wait time for polling."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()
                mock_sqs.receive_message.return_value = {"Messages": []}
                mock_boto.return_value = mock_sqs

                source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                await source.start()

                # Verify receive_message was called with short wait time
                call_args = mock_sqs.receive_message.call_args
                assert call_args[1]["WaitTimeSeconds"] == 1  # Short wait in burst mode
                assert call_args[1]["MaxNumberOfMessages"] == 10  # Get more messages per poll

    @pytest.mark.asyncio
    async def test_burst_mode_initialization(self, mock_config, mock_task_processor):
        """Test that burst mode flag is properly initialized."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_boto.return_value = MagicMock()

                # Default should be False
                source_default = SQSTaskSource(task_processor=mock_task_processor)
                assert source_default._burst_mode is False

                # Explicit burst mode
                source_burst = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                assert source_burst._burst_mode is True

                # Explicit non-burst mode
                source_normal = SQSTaskSource(task_processor=mock_task_processor, burst_mode=False)
                assert source_normal._burst_mode is False

    @pytest.mark.asyncio
    async def test_burst_mode_waits_for_tasks_by_default(self, mock_config, mock_task_processor):
        """Test that burst mode waits for all container tasks to complete by default."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                message = create_sqs_message("msg-1", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": "test-delivery"},
                    "payload": {"action": "opened"}
                })
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [message]},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(task_processor=mock_task_processor, burst_mode=True)
                    result = await source.start()

                # Verify wait_for_all_tasks_complete was called
                mock_task_processor.container_pool.wait_for_all_tasks_complete.assert_called_once()
                assert result.messages_processed == 1
                assert result.tasks_completed == 1

    @pytest.mark.asyncio
    async def test_burst_mode_no_wait_skips_waiting(self, mock_config, mock_task_processor):
        """Test that burst mode with wait_for_tasks=False skips waiting."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                message = create_sqs_message("msg-1", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": "test-delivery"},
                    "payload": {"action": "opened"}
                })
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [message]},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(
                        task_processor=mock_task_processor,
                        burst_mode=True,
                        wait_for_tasks=False
                    )
                    result = await source.start()

                # Verify wait_for_all_tasks_complete was NOT called
                mock_task_processor.container_pool.wait_for_all_tasks_complete.assert_not_called()
                assert result.messages_processed == 1
                assert result.tasks_completed == 0  # Not waiting means no completed count

    @pytest.mark.asyncio
    async def test_burst_mode_with_timeout(self, mock_config, mock_task_processor):
        """Test that burst mode passes timeout to wait_for_all_tasks_complete."""
        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                message = create_sqs_message("msg-1", {
                    "headers": {"x-github-event": "issues", "x-github-delivery": "test-delivery"},
                    "payload": {"action": "opened"}
                })
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [message]},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(
                        task_processor=mock_task_processor,
                        burst_mode=True,
                        task_timeout=3600.0
                    )
                    result = await source.start()

                # Verify wait_for_all_tasks_complete was called with timeout
                mock_task_processor.container_pool.wait_for_all_tasks_complete.assert_called_once_with(
                    timeout=3600.0
                )
                assert result.messages_processed == 1

    @pytest.mark.asyncio
    async def test_burst_mode_timeout_reports_incomplete_tasks(self, mock_config, mock_task_processor):
        """Test that burst mode reports incomplete tasks when timeout occurs."""
        # Set up the mock to return False (timeout) and simulate 1 task still queued
        mock_task_processor.container_pool.wait_for_all_tasks_complete = AsyncMock(return_value=False)
        mock_task_processor.container_pool.get_total_queued_tasks = MagicMock(return_value=1)

        with patch('devs_webhook.sources.sqs_source.get_config', return_value=mock_config):
            with patch('boto3.client') as mock_boto:
                mock_sqs = MagicMock()

                messages = [
                    create_sqs_message("msg-1", {
                        "headers": {"x-github-event": "issues", "x-github-delivery": "delivery-1"},
                        "payload": {"action": "opened"}
                    }),
                    create_sqs_message("msg-2", {
                        "headers": {"x-github-event": "issues", "x-github-delivery": "delivery-2"},
                        "payload": {"action": "opened"}
                    }),
                ]
                mock_sqs.receive_message.side_effect = [
                    {"Messages": messages},
                    {"Messages": []},
                ]
                mock_boto.return_value = mock_sqs

                with patch('devs_webhook.sources.sqs_source.verify_github_signature', return_value=True):
                    source = SQSTaskSource(
                        task_processor=mock_task_processor,
                        burst_mode=True,
                        task_timeout=1.0
                    )
                    result = await source.start()

                # 2 messages processed, but 1 still in queue = 1 completed
                assert result.messages_processed == 2
                assert result.tasks_completed == 1
