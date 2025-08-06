"""Utility modules for devs ecosystem."""

from .file_utils import (
    copy_file_list,
    copy_directory_tree,
    safe_remove_directory,
    ensure_directory_exists,
    get_directory_size,
    is_directory_empty,
)

from .file_utils_async import (
    copy_file_async,
    copy_file_list_async,
    copy_directory_tree_async,
    remove_directory_async,
    ensure_directory_exists_async,
    get_directory_size_async,
    is_directory_empty_async,
)

from .git_utils import (
    get_tracked_files,
    is_git_repository,
)

from .git_utils_async import (
    get_tracked_files_async,
    is_git_repository_async,
    get_git_root_async,
    get_remote_url_async,
    get_current_branch_async,
    clone_repository_async,
    run_git_command,
)

from .docker_client import DockerClient
from .docker_client_async import AsyncDockerClient
from .devcontainer import DevContainerCLI
from .devcontainer_async import AsyncDevContainerCLI

__all__ = [
    # Sync file utils
    "copy_file_list",
    "copy_directory_tree", 
    "safe_remove_directory",
    "ensure_directory_exists",
    "get_directory_size",
    "is_directory_empty",
    # Async file utils
    "copy_file_async",
    "copy_file_list_async",
    "copy_directory_tree_async",
    "remove_directory_async",
    "ensure_directory_exists_async",
    "get_directory_size_async",
    "is_directory_empty_async",
    # Sync git utils
    "get_tracked_files",
    "is_git_repository",
    # Async git utils
    "get_tracked_files_async",
    "is_git_repository_async",
    "get_git_root_async",
    "get_remote_url_async",
    "get_current_branch_async",
    "clone_repository_async",
    "run_git_command",
    # Docker clients
    "DockerClient",
    "AsyncDockerClient",
    # DevContainer CLIs
    "DevContainerCLI",
    "AsyncDevContainerCLI",
]