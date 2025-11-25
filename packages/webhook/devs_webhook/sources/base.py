"""Base interface for task sources."""

from abc import ABC, abstractmethod


class TaskSource(ABC):
    """Abstract interface for task sources that feed tasks into the webhook handler.

    A task source is responsible for receiving task requests from external systems
    (webhooks, queues, etc.) and forwarding them to the task processor.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start receiving and processing tasks.

        This method should block until the task source is stopped.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop receiving tasks and clean up resources."""
        pass
