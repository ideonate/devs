"""DevContainer Management Tool

A command-line tool that simplifies managing multiple named devcontainers for any project.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("devs-cli")
except PackageNotFoundError:
    __version__ = "0.0.0"
__author__ = "Dan Lester"
__email__ = "dan@ideonate.com"

from devs_common.core import Project, ContainerManager, WorkspaceManager
from .core.integration import VSCodeIntegration

__all__ = [
    "Project",
    "ContainerManager", 
    "WorkspaceManager",
    "VSCodeIntegration",
]