"""Custom exceptions for devs package."""

# Import from common package for compatibility
from devs_common.exceptions import (
    DevsError,
    ProjectNotFoundError,
    DevcontainerConfigError,
    ContainerError,
    DockerError,
    WorkspaceError,
    VSCodeError,
    DependencyError,
)

__all__ = [
    "DevsError",
    "ProjectNotFoundError", 
    "DevcontainerConfigError",
    "ContainerError",
    "DockerError",
    "WorkspaceError",
    "VSCodeError",
    "DependencyError",
]