"""Sync wrappers for async functionality from devs_common."""

import asyncio
from pathlib import Path
from typing import List, Optional, Tuple

from devs_common.core import (
    Project,
    AsyncContainerManager,
    AsyncWorkspaceManager,
    ContainerInfo
)
from devs_common.config import BaseConfig


def run_async(coro):
    """Run an async coroutine in a sync context."""
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop
        pass
    
    if loop and loop.is_running():
        # We're already in an async context, create a new thread
        import concurrent.futures
        import threading
        
        result = None
        exception = None
        
        def run_in_thread():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if exception:
            raise exception
        return result
    else:
        # No running loop, we can create one
        return asyncio.run(coro)


class SyncContainerManager:
    """Sync wrapper for AsyncContainerManager."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize sync container manager."""
        self.async_manager = AsyncContainerManager(project, config)
        self.project = project
        self.config = config
    
    def should_rebuild_image(self, dev_name: str) -> Tuple[bool, str]:
        """Check if devcontainer image should be rebuilt."""
        return run_async(self.async_manager.should_rebuild_image(dev_name))
    
    def ensure_container_running(
        self, 
        dev_name: str, 
        workspace_dir: Path,
        rebuild: bool = False,
        debug: bool = False
    ) -> bool:
        """Ensure container is running for the dev environment."""
        return run_async(
            self.async_manager.ensure_container_running(
                dev_name, workspace_dir, rebuild, debug
            )
        )
    
    def stop_container(self, dev_name: str) -> bool:
        """Stop and remove a container."""
        return run_async(self.async_manager.stop_container(dev_name))
    
    def list_containers(self) -> List[ContainerInfo]:
        """List all containers for the current project."""
        return run_async(self.async_manager.list_containers())
    
    def find_aborted_containers(self, all_projects: bool = False) -> List[ContainerInfo]:
        """Find aborted devs containers that failed during setup."""
        return run_async(self.async_manager.find_aborted_containers(all_projects))
    
    def remove_aborted_containers(self, containers: List[ContainerInfo]) -> int:
        """Remove a list of aborted containers."""
        return run_async(self.async_manager.remove_aborted_containers(containers))
    
    def exec_shell(self, dev_name: str, workspace_dir: Path, debug: bool = False) -> None:
        """Execute an interactive shell in the container."""
        # This needs special handling for TTY
        return run_async(self.async_manager.exec_shell(dev_name, workspace_dir, debug))
    
    def exec_claude(
        self, 
        dev_name: str, 
        workspace_dir: Path, 
        prompt: str, 
        debug: bool = False,
        stream: bool = True
    ) -> tuple[bool, str, str]:
        """Execute Claude CLI in the container."""
        return run_async(
            self.async_manager.exec_claude_async(dev_name, workspace_dir, prompt, debug)
        )
    
    # Provide compatibility with existing sync interface
    def exec_claude_async(
        self, 
        dev_name: str, 
        workspace_dir: Path, 
        prompt: str, 
        debug: bool = False
    ) -> tuple[bool, str, str]:
        """Execute Claude CLI in the container (async compatibility method)."""
        return self.exec_claude(dev_name, workspace_dir, prompt, debug)


class SyncWorkspaceManager:
    """Sync wrapper for AsyncWorkspaceManager."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize sync workspace manager."""
        self.async_manager = AsyncWorkspaceManager(project, config)
        self.project = project
        self.config = config
        # Mirror the workspaces_dir property
        self.workspaces_dir = self.async_manager.workspaces_dir
    
    def get_workspace_dir(self, dev_name: str) -> Path:
        """Get workspace directory path for a dev environment."""
        return self.async_manager.get_workspace_dir(dev_name)
    
    def workspace_exists(self, dev_name: str) -> bool:
        """Check if workspace directory exists."""
        return run_async(self.async_manager.workspace_exists(dev_name))
    
    def create_workspace(self, dev_name: str, reset_contents: bool = False) -> Path:
        """Create isolated workspace directory for a dev environment."""
        return run_async(self.async_manager.create_workspace(dev_name, reset_contents))
    
    def remove_workspace(self, dev_name: str, contents_only: bool = False) -> bool:
        """Remove workspace directory for a dev environment."""
        return run_async(self.async_manager.remove_workspace(dev_name, contents_only))
    
    def list_workspaces(self) -> List[str]:
        """List all workspace directories for the current project."""
        return run_async(self.async_manager.list_workspaces())
    
    def cleanup_unused_workspaces(self, active_dev_names: List[str]) -> int:
        """Clean up workspaces not associated with active containers."""
        return run_async(self.async_manager.cleanup_unused_workspaces(active_dev_names))
    
    def find_orphaned_workspaces(self) -> List[str]:
        """Find workspace directories without corresponding containers."""
        return run_async(self.async_manager.find_orphaned_workspaces())