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


class WorkspaceError(DevsError):
    """Raised when workspace operations fail."""
    pass


class VSCodeError(DevsError):
    """Raised when VS Code integration fails."""
    pass


class DependencyError(DevsError):
    """Raised when required dependencies are missing."""
    pass