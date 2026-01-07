"""Custom exceptions for devs package ecosystem."""


class DevsError(Exception):
    """Base exception for all devs-related errors."""
    pass


class ProjectNotFoundError(DevsError):
    """Raised when project information cannot be determined."""
    pass


class DevcontainerConfigError(DevsError):
    """Raised when devcontainer configuration is invalid or missing."""
    pass


class ContainerError(DevsError):
    """Raised when container operations fail."""
    pass


class DockerError(ContainerError):
    """Raised when Docker operations fail."""
    pass


class PortConflictError(ContainerError):
    """Raised when a port conflict is detected during container startup."""

    def __init__(self, port: str, message: str = ""):
        self.port = port
        if not message:
            message = f"Port {port} is already in use by another process"
        super().__init__(message)


class WorkspaceError(DevsError):
    """Raised when workspace operations fail."""
    pass


class VSCodeError(DevsError):
    """Raised when VS Code integration fails."""
    pass


class DependencyError(DevsError):
    """Raised when required dependencies are missing."""
    pass