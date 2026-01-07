"""Tests for Docker error parsing functions."""
import pytest

from devs_common.utils.devcontainer import (
    parse_docker_error,
    format_port_conflict_error,
)
from devs_common.exceptions import PortConflictError


class TestParseDockerError:
    """Test suite for parse_docker_error function."""

    def test_port_conflict_error(self):
        """Test parsing port already allocated error."""
        error_output = (
            "docker: Error response from daemon: failed to set up container networking: "
            "driver failed programming external connectivity on endpoint practical_gould "
            "(92ab6d2262aa7b043091b856720ed3cc1085a1baae282a9f8fdd79ef5ecedba2): "
            "Bind for 0.0.0.0:5002 failed: port is already allocated"
        )

        error_type, details = parse_docker_error(error_output)

        assert error_type == 'port_conflict'
        assert details == '5002'

    def test_port_conflict_different_port(self):
        """Test parsing port conflict with different port number."""
        error_output = "Bind for 0.0.0.0:8080 failed: port is already allocated"

        error_type, details = parse_docker_error(error_output)

        assert error_type == 'port_conflict'
        assert details == '8080'

    def test_port_conflict_ipv6(self):
        """Test parsing port conflict with IPv6 address."""
        error_output = "Bind for [::]:3000 failed: port is already allocated"

        error_type, details = parse_docker_error(error_output)

        assert error_type == 'port_conflict'
        assert details == '3000'

    def test_docker_daemon_not_running(self):
        """Test parsing Docker daemon not running error."""
        error_output = (
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running?"
        )

        error_type, details = parse_docker_error(error_output)

        assert error_type == 'daemon_not_running'
        assert details is None

    def test_generic_error_returns_none(self):
        """Test that generic errors return None."""
        error_output = "Some random error message that doesn't match any pattern"

        error_type, details = parse_docker_error(error_output)

        assert error_type is None
        assert details is None

    def test_empty_output(self):
        """Test parsing empty error output."""
        error_type, details = parse_docker_error("")

        assert error_type is None
        assert details is None

    def test_image_not_found_error(self):
        """Test parsing image pull access denied error."""
        error_output = "pull access denied for myregistry/myimage, repository does not exist"

        error_type, details = parse_docker_error(error_output)

        assert error_type == 'image_not_found'


class TestFormatPortConflictError:
    """Test suite for format_port_conflict_error function."""

    def test_format_includes_port_number(self):
        """Test that formatted message includes the port number."""
        message = format_port_conflict_error("5002")

        assert "5002" in message
        assert "already in use" in message

    def test_format_includes_lsof_command(self):
        """Test that formatted message includes lsof command."""
        message = format_port_conflict_error("8080")

        assert "lsof -ti:8080" in message

    def test_format_includes_kill_command(self):
        """Test that formatted message includes kill command."""
        message = format_port_conflict_error("3000")

        assert "kill -9" in message

    def test_format_includes_devs_commands(self):
        """Test that formatted message includes devs commands."""
        message = format_port_conflict_error("5002")

        assert "devs list" in message
        assert "devs stop" in message


class TestPortConflictError:
    """Test suite for PortConflictError exception."""

    def test_exception_stores_port(self):
        """Test that exception stores the port number."""
        error = PortConflictError("5002")

        assert error.port == "5002"

    def test_exception_default_message(self):
        """Test exception default message."""
        error = PortConflictError("8080")

        assert "8080" in str(error)
        assert "already in use" in str(error)

    def test_exception_custom_message(self):
        """Test exception with custom message."""
        error = PortConflictError("3000", "Custom error message")

        assert error.port == "3000"
        assert str(error) == "Custom error message"

    def test_exception_inherits_from_container_error(self):
        """Test that PortConflictError inherits from ContainerError."""
        from devs_common.exceptions import ContainerError

        error = PortConflictError("5002")

        assert isinstance(error, ContainerError)
