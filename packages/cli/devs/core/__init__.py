"""Core functionality for devcontainer management."""

# Import from common package
from devs_common.core.project import Project, ProjectInfo
from devs_common.core.container import ContainerInfo

# Import sync wrappers for CLI usage
from .async_wrappers import SyncContainerManager as ContainerManager
from .async_wrappers import SyncWorkspaceManager as WorkspaceManager

__all__ = ["Project", "ProjectInfo", "WorkspaceManager", "ContainerManager", "ContainerInfo"]