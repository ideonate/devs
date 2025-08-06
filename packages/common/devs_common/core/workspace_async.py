"""Async workspace management for isolated dev environments."""

import asyncio
from pathlib import Path
from typing import List, Optional

from ..config import BaseConfig
from ..exceptions import WorkspaceError
from ..utils.file_utils_async import (
    copy_file_list_async,
    copy_directory_tree_async,
    remove_directory_async,
    is_directory_empty_async,
    ensure_directory_exists_async
)
from ..utils.git_utils_async import (
    get_tracked_files_async,
    is_git_repository_async
)
from ..utils.docker_client_async import AsyncDockerClient
from .project import Project


class AsyncWorkspaceManager:
    """Async manager for isolated workspace directories for dev environments."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize async workspace manager.
        
        Args:
            project: Project instance
            config: Configuration instance (optional)
        """
        self.project = project
        self.config = config
        
        # Set default workspaces directory if not provided
        if self.config:
            self.workspaces_dir = self.config.workspaces_dir
        else:
            self.workspaces_dir = Path.home() / ".devs" / "workspaces"
    
    async def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        await ensure_directory_exists_async(self.workspaces_dir)
    
    def get_workspace_dir(self, dev_name: str) -> Path:
        """Get workspace directory path for a dev environment.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Path to workspace directory
        """
        workspace_name = self.project.get_workspace_name(dev_name)
        return self.workspaces_dir / workspace_name
    
    async def workspace_exists(self, dev_name: str) -> bool:
        """Check if workspace directory exists.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            True if workspace exists
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        return workspace_dir.exists()
    
    async def create_workspace(self, dev_name: str, reset_contents: bool = False) -> Path:
        """Create isolated workspace directory for a dev environment.
        
        Args:
            dev_name: Development environment name
            reset_contents: If True, clear and recreate workspace contents
            
        Returns:
            Path to created workspace directory
            
        Raises:
            WorkspaceError: If workspace creation fails
        """
        await self._ensure_directories()
        
        workspace_dir = self.get_workspace_dir(dev_name)
        
        try:
            # Create workspace directory
            await ensure_directory_exists_async(workspace_dir)
            
            # Check if we should reset contents
            if reset_contents or await is_directory_empty_async(workspace_dir):
                # Copy project files to workspace
                if self.project.info.is_git:
                    await self._copy_git_tracked_files(workspace_dir)
                else:
                    await self._copy_all_files(workspace_dir)
                
                # Copy special directories
                await self._copy_special_directories(workspace_dir)
            
            return workspace_dir
            
        except Exception as e:
            raise WorkspaceError(f"Failed to create workspace: {e}")
    
    async def _copy_git_tracked_files(self, workspace_dir: Path) -> None:
        """Copy git-tracked files to workspace.
        
        Args:
            workspace_dir: Target workspace directory
            
        Raises:
            WorkspaceError: If copying fails
        """
        try:
            # Get list of tracked files
            tracked_files = await get_tracked_files_async(self.project.project_dir)
            
            if not tracked_files:
                raise WorkspaceError("No tracked files found in git repository")
            
            # Copy tracked files to workspace
            await copy_file_list_async(
                source_dir=self.project.project_dir,
                dest_dir=workspace_dir,
                file_list=tracked_files,
                preserve_permissions=True
            )
            
        except Exception as e:
            raise WorkspaceError(f"Failed to copy git-tracked files: {e}")
    
    async def _copy_all_files(self, workspace_dir: Path) -> None:
        """Copy all files (non-git repository) to workspace.
        
        Args:
            workspace_dir: Target workspace directory
            
        Raises:
            WorkspaceError: If copying fails
        """
        try:
            # Define exclusion patterns for common build/cache directories
            exclude_patterns = {
                'node_modules', '**/node_modules',
                '__pycache__', '**/__pycache__',
                '.pytest_cache', '**/.pytest_cache',
                'target', '**/target',  # Rust/Java
                'build', '**/build',
                'dist', '**/dist',
                '.venv', '**/.venv',
                'venv', '**/venv',
                '.env', '**/.env',
                '*.pyc', '**/*.pyc',
                '.DS_Store', '**/.DS_Store',
            }
            
            # Copy entire directory tree with exclusions
            await copy_directory_tree_async(
                source_dir=self.project.project_dir,
                dest_dir=workspace_dir,
                exclude_patterns=exclude_patterns,
                preserve_permissions=True
            )
            
        except Exception as e:
            raise WorkspaceError(f"Failed to copy project files: {e}")
    
    async def _copy_special_directories(self, workspace_dir: Path) -> None:
        """Copy special directories like .git, .claude, .devcontainer extras.
        
        Args:
            workspace_dir: Target workspace directory
            
        Raises:
            WorkspaceError: If copying fails
        """
        special_dirs = ['.git', '.claude']
        
        for dir_name in special_dirs:
            source = self.project.project_dir / dir_name
            if source.exists() and source.is_dir():
                dest = workspace_dir / dir_name
                
                # Remove destination if it exists
                if dest.exists():
                    await remove_directory_async(dest)
                
                # Copy the directory
                try:
                    await copy_directory_tree_async(
                        source_dir=source,
                        dest_dir=dest,
                        preserve_permissions=True
                    )
                except Exception:
                    # Non-critical, continue
                    pass
        
        # Copy .devcontainer/.env file if it exists
        devcontainer_env = self.project.project_dir / '.devcontainer' / '.env'
        if devcontainer_env.exists():
            dest_devcontainer = workspace_dir / '.devcontainer'
            await ensure_directory_exists_async(dest_devcontainer)
            
            from ..utils.file_utils_async import copy_file_async
            try:
                await copy_file_async(
                    devcontainer_env,
                    dest_devcontainer / '.env',
                    preserve_permissions=True
                )
            except Exception:
                # Non-critical, continue
                pass
    
    async def remove_workspace(self, dev_name: str, contents_only: bool = False) -> bool:
        """Remove workspace directory for a dev environment.
        
        Args:
            dev_name: Development environment name
            contents_only: If True, only remove contents, not the directory itself
            
        Returns:
            True if workspace was removed
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        
        if not workspace_dir.exists():
            return False
        
        try:
            if contents_only:
                # Remove only contents
                for item in workspace_dir.iterdir():
                    if item.is_dir():
                        await remove_directory_async(item)
                    else:
                        item.unlink()
            else:
                # Remove entire directory
                await remove_directory_async(workspace_dir)
            
            return True
            
        except Exception:
            return False
    
    async def list_workspaces(self) -> List[str]:
        """List all workspace directories for the current project.
        
        Returns:
            List of dev environment names
        """
        await self._ensure_directories()
        
        workspaces = []
        prefix = f"{self.project.info.name}-"
        
        if self.workspaces_dir.exists():
            for workspace_dir in self.workspaces_dir.iterdir():
                if workspace_dir.is_dir() and workspace_dir.name.startswith(prefix):
                    # Extract dev name from workspace directory name
                    dev_name = workspace_dir.name[len(prefix):]
                    workspaces.append(dev_name)
        
        return workspaces
    
    async def cleanup_unused_workspaces(self, active_dev_names: List[str]) -> int:
        """Clean up workspaces not associated with active containers.
        
        Args:
            active_dev_names: List of active dev environment names
            
        Returns:
            Number of workspaces removed
        """
        removed_count = 0
        all_workspaces = await self.list_workspaces()
        
        for dev_name in all_workspaces:
            if dev_name not in active_dev_names:
                if await self.remove_workspace(dev_name):
                    removed_count += 1
        
        return removed_count
    
    async def find_orphaned_workspaces(self) -> List[str]:
        """Find workspace directories without corresponding containers.
        
        Returns:
            List of orphaned dev environment names
        """
        # Get all workspaces for this project
        all_workspaces = await self.list_workspaces()
        
        # Get active containers
        async with AsyncDockerClient() as docker:
            try:
                labels = {'devs.project': self.project.info.name}
                containers = await docker.find_containers_by_labels(labels)
                
                active_dev_names = [
                    container['labels'].get('devs.dev', '')
                    for container in containers
                ]
                
                # Find orphaned workspaces
                orphaned = [
                    dev_name for dev_name in all_workspaces
                    if dev_name not in active_dev_names
                ]
                
                return orphaned
                
            except Exception:
                # If we can't check containers, return all workspaces as potentially orphaned
                return all_workspaces