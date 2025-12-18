"""Container output logging for CloudWatch compatibility.

This module provides utilities to write container output (stdout/stderr) to
log files in a format that CloudWatch agent can easily pick up.

Log files are written to:
    {container_logs_dir}/{container_name}/{task_id}.log

Each log entry is a JSON line (JSONL format) for easy parsing by CloudWatch.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger()


class ContainerLogWriter:
    """Writes container output to CloudWatch-compatible log files.

    Creates log files in JSONL (JSON Lines) format where each line is a
    self-contained JSON object. This format is ideal for CloudWatch agent
    ingestion and allows for structured log queries.

    Log file structure:
        {logs_dir}/{container_name}/{task_id}.log

    Each line in the log file is a JSON object with:
        - timestamp: ISO 8601 timestamp
        - container: Container name
        - task_id: Unique task identifier
        - repo: Repository name (owner/repo)
        - stream: "stdout" or "stderr"
        - content: The actual log content
        - metadata: Additional context (event type, task type, etc.)
    """

    def __init__(
        self,
        logs_dir: Path,
        container_name: str,
        task_id: str,
        repo_name: str,
        task_type: str = "claude",
    ):
        """Initialize the container log writer.

        Args:
            logs_dir: Base directory for container logs
            container_name: Name of the container (e.g., "eamonn")
            task_id: Unique task identifier
            repo_name: Repository name (owner/repo format)
            task_type: Type of task ("claude" or "tests")
        """
        self.logs_dir = logs_dir
        self.container_name = container_name
        self.task_id = task_id
        self.repo_name = repo_name
        self.task_type = task_type

        # Create container-specific log directory
        self.container_log_dir = logs_dir / container_name
        self.container_log_dir.mkdir(parents=True, exist_ok=True)

        # Log file path: {container_name}/{task_id}.log
        self.log_file = self.container_log_dir / f"{task_id}.log"

        # Track if we've written any logs
        self._started = False
        self._start_time: Optional[datetime] = None

    def _write_entry(
        self,
        stream: str,
        content: str,
        event_type: Optional[str] = None,
        **extra_metadata
    ) -> None:
        """Write a single log entry to the log file.

        Args:
            stream: Log stream ("stdout", "stderr", or "system")
            content: Log content to write
            event_type: Optional event type (e.g., "start", "output", "end")
            **extra_metadata: Additional metadata to include (added at top level)
        """
        timestamp = datetime.now(timezone.utc)

        entry = {
            "timestamp": timestamp.isoformat(),
            "container": self.container_name,
            "task_id": self.task_id,
            "repo": self.repo_name,
            "task_type": self.task_type,
            "stream": stream,
            "event_type": event_type or "output",
            "content": content,
        }

        # Add extra metadata at the top level for easy CloudWatch querying
        # (flat structure is easier to query than nested)
        entry.update(extra_metadata)

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to write container log entry",
                        task_id=self.task_id,
                        container=self.container_name,
                        error=str(e))

    def start(self, prompt: Optional[str] = None, **metadata) -> None:
        """Log the start of a task execution.

        Args:
            prompt: Optional prompt being executed (for Claude tasks)
            **metadata: Additional metadata to include
        """
        self._started = True
        self._start_time = datetime.now(timezone.utc)

        content = f"Task started: {self.task_type} execution in container {self.container_name}"
        if prompt:
            # Include truncated prompt for context
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            metadata["prompt_preview"] = prompt_preview

        self._write_entry(
            stream="system",
            content=content,
            event_type="start",
            **metadata
        )

        logger.info("Container log started",
                   task_id=self.task_id,
                   container=self.container_name,
                   log_file=str(self.log_file))

    def write_stdout(self, content: str) -> None:
        """Write stdout content to the log.

        Args:
            content: Stdout content to log
        """
        if not content:
            return
        self._write_entry(stream="stdout", content=content)

    def write_stderr(self, content: str) -> None:
        """Write stderr content to the log.

        Args:
            content: Stderr content to log
        """
        if not content:
            return
        self._write_entry(stream="stderr", content=content)

    def write_output(self, stdout: str, stderr: str) -> None:
        """Write both stdout and stderr to the log.

        Args:
            stdout: Standard output content
            stderr: Standard error content
        """
        if stdout:
            self.write_stdout(stdout)
        if stderr:
            self.write_stderr(stderr)

    def end(
        self,
        success: bool,
        exit_code: Optional[int] = None,
        error: Optional[str] = None,
        **metadata
    ) -> None:
        """Log the end of a task execution.

        Args:
            success: Whether the task succeeded
            exit_code: Optional exit code from the container
            error: Optional error message if failed
            **metadata: Additional metadata to include
        """
        duration_seconds = None
        if self._start_time:
            duration = datetime.now(timezone.utc) - self._start_time
            duration_seconds = duration.total_seconds()

        status = "success" if success else "failed"
        content = f"Task {status}"
        if exit_code is not None:
            content += f" (exit code: {exit_code})"
        if error:
            content += f": {error[:200]}"

        # Include success, exit_code, duration in metadata for structured querying
        metadata["success"] = success
        metadata["exit_code"] = exit_code
        metadata["duration_seconds"] = duration_seconds
        if error:
            metadata["error"] = error[:1000]

        self._write_entry(
            stream="system",
            content=content,
            event_type="end",
            **metadata
        )

        logger.info("Container log completed",
                   task_id=self.task_id,
                   container=self.container_name,
                   success=success,
                   duration_seconds=duration_seconds,
                   log_file=str(self.log_file))


def create_container_log_writer(
    config,  # WebhookConfig
    container_name: str,
    task_id: str,
    repo_name: str,
    task_type: str = "claude",
) -> Optional[ContainerLogWriter]:
    """Create a ContainerLogWriter if container logging is enabled.

    Factory function that checks config and returns a writer only if
    container logging is enabled.

    Args:
        config: WebhookConfig instance
        container_name: Name of the container
        task_id: Unique task identifier
        repo_name: Repository name (owner/repo format)
        task_type: Type of task ("claude" or "tests")

    Returns:
        ContainerLogWriter if logging is enabled, None otherwise
    """
    if not config.container_logs_enabled:
        return None

    return ContainerLogWriter(
        logs_dir=config.container_logs_dir,
        container_name=container_name,
        task_id=task_id,
        repo_name=repo_name,
        task_type=task_type,
    )
