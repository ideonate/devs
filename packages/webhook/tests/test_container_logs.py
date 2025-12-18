"""Tests for container log writer functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from devs_webhook.utils.container_logs import (
    ContainerLogWriter,
    create_container_log_writer,
)


class TestContainerLogWriter:
    """Tests for ContainerLogWriter class."""

    def test_creates_log_directory(self, tmp_path):
        """Test that log directory is created."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="eamonn",
            task_id="test-123",
            repo_name="owner/repo",
            task_type="claude"
        )

        assert (tmp_path / "eamonn").exists()
        assert writer.log_file == tmp_path / "eamonn" / "test-123.log"

    def test_writes_start_entry(self, tmp_path):
        """Test writing start entry."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="harry",
            task_id="task-456",
            repo_name="org/project",
            task_type="tests"
        )

        writer.start(prompt="Test prompt here")

        assert writer.log_file.exists()
        with open(writer.log_file) as f:
            entry = json.loads(f.read().strip())

        assert entry["container"] == "harry"
        assert entry["task_id"] == "task-456"
        assert entry["repo"] == "org/project"
        assert entry["task_type"] == "tests"
        assert entry["stream"] == "system"
        assert entry["event_type"] == "start"
        assert "prompt_preview" in entry  # Metadata is at top level for CloudWatch

    def test_writes_stdout(self, tmp_path):
        """Test writing stdout content."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="darren",
            task_id="task-789",
            repo_name="owner/repo",
            task_type="claude"
        )

        writer.write_stdout("This is stdout content")

        with open(writer.log_file) as f:
            entry = json.loads(f.read().strip())

        assert entry["stream"] == "stdout"
        assert entry["content"] == "This is stdout content"

    def test_writes_stderr(self, tmp_path):
        """Test writing stderr content."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="eamonn",
            task_id="task-abc",
            repo_name="owner/repo",
            task_type="claude"
        )

        writer.write_stderr("Error message here")

        with open(writer.log_file) as f:
            entry = json.loads(f.read().strip())

        assert entry["stream"] == "stderr"
        assert entry["content"] == "Error message here"

    def test_writes_end_entry_success(self, tmp_path):
        """Test writing end entry for successful task."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="harry",
            task_id="task-def",
            repo_name="owner/repo",
            task_type="tests"
        )

        writer.start()
        writer.end(success=True, exit_code=0)

        with open(writer.log_file) as f:
            lines = f.read().strip().split('\n')

        assert len(lines) == 2
        end_entry = json.loads(lines[1])

        assert end_entry["event_type"] == "end"
        assert end_entry["success"] is True
        assert end_entry["exit_code"] == 0
        assert "duration_seconds" in end_entry

    def test_writes_end_entry_failure(self, tmp_path):
        """Test writing end entry for failed task."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="darren",
            task_id="task-ghi",
            repo_name="owner/repo",
            task_type="claude"
        )

        writer.end(success=False, exit_code=1, error="Something went wrong")

        with open(writer.log_file) as f:
            entry = json.loads(f.read().strip())

        assert entry["event_type"] == "end"
        assert entry["success"] is False
        assert entry["exit_code"] == 1
        assert "Something went wrong" in entry["error"]

    def test_write_output_both_streams(self, tmp_path):
        """Test write_output writes both stdout and stderr."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="eamonn",
            task_id="task-jkl",
            repo_name="owner/repo",
            task_type="tests"
        )

        writer.write_output("stdout content", "stderr content")

        with open(writer.log_file) as f:
            lines = f.read().strip().split('\n')

        assert len(lines) == 2
        stdout_entry = json.loads(lines[0])
        stderr_entry = json.loads(lines[1])

        assert stdout_entry["stream"] == "stdout"
        assert stderr_entry["stream"] == "stderr"

    def test_skips_empty_content(self, tmp_path):
        """Test that empty content is not written."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="harry",
            task_id="task-mno",
            repo_name="owner/repo",
            task_type="claude"
        )

        writer.write_stdout("")
        writer.write_stderr("")
        writer.write_output("", "")

        # File should not exist or be empty since nothing was written
        if writer.log_file.exists():
            assert writer.log_file.read_text() == ""

    def test_full_task_lifecycle(self, tmp_path):
        """Test a complete task lifecycle."""
        writer = ContainerLogWriter(
            logs_dir=tmp_path,
            container_name="eamonn",
            task_id="task-full",
            repo_name="myorg/myrepo",
            task_type="claude"
        )

        # Start task
        writer.start(prompt="Build a feature", issue_number=123)

        # Write some output
        writer.write_stdout("Processing...")
        writer.write_stdout("Building feature...")
        writer.write_stderr("Warning: something minor")

        # End task
        writer.end(success=True)

        # Verify log file
        with open(writer.log_file) as f:
            lines = f.read().strip().split('\n')

        assert len(lines) == 5  # start + 2 stdout + 1 stderr + end

        entries = [json.loads(line) for line in lines]

        # All entries have common fields
        for entry in entries:
            assert entry["container"] == "eamonn"
            assert entry["task_id"] == "task-full"
            assert entry["repo"] == "myorg/myrepo"
            assert "timestamp" in entry


class TestCreateContainerLogWriter:
    """Tests for create_container_log_writer factory function."""

    def test_returns_none_when_disabled(self, tmp_path):
        """Test that factory returns None when logging is disabled."""
        config = MagicMock()
        config.container_logs_enabled = False

        writer = create_container_log_writer(
            config=config,
            container_name="eamonn",
            task_id="test-123",
            repo_name="owner/repo"
        )

        assert writer is None

    def test_returns_writer_when_enabled(self, tmp_path):
        """Test that factory returns writer when logging is enabled."""
        config = MagicMock()
        config.container_logs_enabled = True
        config.container_logs_dir = tmp_path

        writer = create_container_log_writer(
            config=config,
            container_name="harry",
            task_id="test-456",
            repo_name="owner/repo",
            task_type="tests"
        )

        assert writer is not None
        assert isinstance(writer, ContainerLogWriter)
        assert writer.container_name == "harry"
        assert writer.task_type == "tests"
