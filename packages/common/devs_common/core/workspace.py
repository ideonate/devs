"""Workspace management and isolation."""

import os
import sys
import shutil
from pathlib import Path
from typing import List, Optional, Set

from rich.console import Console

from ..config import BaseConfig
from ..exceptions import WorkspaceError
from ..utils.file_utils import (
    copy_file_list,
    copy_directory_tree,
    ensure_directory_exists,
    safe_remove_directory,
    is_directory_empty
)
from ..utils.git_utils import get_tracked_files, is_git_repository
from .project import Project

# Initialize Rich console
# When running in webhook mode, output to stderr to avoid mixing with JSON output
if os.environ.get('DEVS_WEBHOOK_MODE') == '1':
    console = Console(stderr=True)
else:
    console = Console()


class WorkspaceManager:
    """Manages isolated workspace directories for dev environments."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize workspace manager.
        
        Args:
            project: Project instance
            config: Configuration instance (optional)
        """
        self.project = project
        self.config = config
        if self.config:
            self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        if self.config:
            self.config.ensure_directories()
    
    def get_workspace_dir(self, dev_name: str) -> Path:
        """Get workspace directory path for a dev environment.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Path to workspace directory
        """
        workspace_name = f"{self.project.info.name}-{dev_name}"
        if self.config:
            return self.config.workspaces_dir / workspace_name
        else:
            # Fallback for when no config is provided
            return Path.home() / ".devs-webhook" / "workspaces" / workspace_name
    
    def workspace_exists(self, dev_name: str) -> bool:
        """Check if workspace directory exists.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            True if workspace exists
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        return workspace_dir.exists() and not is_directory_empty(workspace_dir)
    
    def create_workspace(self, dev_name: str, reset_contents: bool = False) -> Path:
        """Create isolated workspace directory for a dev environment.
        
        Args:
            dev_name: Development environment name
            reset_contents: Force contents clear if workspace already exists
            
        Returns:
            Path to created workspace directory
            
        Raises:
            WorkspaceError: If workspace creation fails
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        
        # Check if workspace already exists
        if self.workspace_exists(dev_name):
            if reset_contents:
                console.print(f"   🗑️  Resetting existing workspace for {dev_name}...")
                self.remove_workspace(dev_name, contents_only=True)
            else:
                console.print(f"   📁 Using existing workspace at {workspace_dir}")
                return workspace_dir
        
        console.print(f"   📂 Creating isolated workspace copy for {dev_name}...")
        
        try:
            # Ensure workspace directory exists
            ensure_directory_exists(workspace_dir)
            
            # Copy files based on whether this is a git repository
            if self.project.info.is_git_repo:
                self._copy_git_tracked_files(workspace_dir)
            else:
                self._copy_all_files(workspace_dir)
            
            # Copy special directories
            self._copy_special_directories(workspace_dir)
            
            # Don't copy devcontainer template - will use external config if needed
            
            console.print(f"   ✅ Directory copied to {workspace_dir}")
            return workspace_dir
            
        except Exception as e:
            # Clean up on failure
            if workspace_dir.exists():
                safe_remove_directory(workspace_dir)
            raise WorkspaceError(f"Failed to create workspace for {dev_name}: {e}")
    
    def _copy_git_tracked_files(self, workspace_dir: Path) -> None:
        """Copy git-tracked files to workspace.
        
        Args:
            workspace_dir: Destination workspace directory
        """
        try:
            tracked_files = get_tracked_files(self.project.project_dir)
            copy_file_list(
                source_dir=self.project.project_dir,
                dest_dir=workspace_dir,
                file_list=tracked_files,
                preserve_permissions=True
            )
        except Exception as e:
            raise WorkspaceError(f"Failed to copy git-tracked files: {e}")
    
    def _copy_all_files(self, workspace_dir: Path) -> None:
        """Copy all files (non-git repository) to workspace.
        
        Args:
            workspace_dir: Destination workspace directory
        """
        # Exclude common build/cache directories
        exclude_patterns = {
            '**/__pycache__',
            '**/node_modules', 
            '**/target',
            '**/build',
            '**/dist',
            '**/.pytest_cache',
            '**/.mypy_cache',
            '**/.tox',
            '**/venv',
            '**/env',
            '**/.env',
            '**/.venv',
        }
        
        try:
            copy_directory_tree(
                source_dir=self.project.project_dir,
                dest_dir=workspace_dir,
                exclude_patterns=exclude_patterns,
                preserve_permissions=True
            )
        except Exception as e:
            raise WorkspaceError(f"Failed to copy project files: {e}")
    
    def _copy_special_directories(self, workspace_dir: Path) -> None:
        """Copy special directories like .git, .claude, .devcontainer extras.
        
        Args:
            workspace_dir: Destination workspace directory
        """
        special_dirs = [
            ('.git', True),  # (source_name, required)
            ('.claude', False),
        ]
        
        for dir_name, required in special_dirs:
            source_dir = self.project.project_dir / dir_name
            dest_dir = workspace_dir / dir_name
            
            if source_dir.exists():
                try:
                    if source_dir.is_dir():
                        shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source_dir, dest_dir)
                    console.print(f"   📋 Copied {dir_name}/")
                except Exception as e:
                    if required:
                        raise WorkspaceError(f"Failed to copy required directory {dir_name}: {e}")
                    else:
                        console.print(f"   ⚠️  Warning: Could not copy {dir_name}: {e}")
        
        # Copy specific devcontainer files if they exist
        # Note: .env files are optional since GH_TOKEN is now passed via environment
        devcontainer_extras = [
            '.devcontainer/.env',  # Optional: only needed if project has custom env vars
            '.devcontainer/.ssh',
        ]
        
        for extra_path in devcontainer_extras:
            source_path = self.project.project_dir / extra_path
            dest_path = workspace_dir / extra_path
            
            if source_path.exists():
                try:
                    ensure_directory_exists(dest_path.parent)
                    
                    if source_path.is_dir():
                        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source_path, dest_path)
                    
                    console.print(f"   📋 Copied {extra_path}")
                except Exception as e:
                    console.print(f"   ⚠️  Warning: Could not copy {extra_path}: {e}")
    
    def remove_workspace(self, dev_name: str, contents_only: bool = False) -> bool:
        """Remove workspace directory for a dev environment.
        
        Args:
            dev_name: Development environment name
            contents_only: If True, remove only contents but keep the directory
            
        Returns:
            True if workspace was removed
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        
        if not workspace_dir.exists():
            return False
        
        try:
            if contents_only:
                # Remove all contents but keep the directory itself
                for item in workspace_dir.iterdir():
                    if item.is_dir():
                        safe_remove_directory(item)
                    else:
                        item.unlink()
                console.print(f"   🗑️  Removed workspace contents: {workspace_dir}")
            else:
                safe_remove_directory(workspace_dir)
                console.print(f"   🗑️  Removed workspace: {workspace_dir}")
            return True
        except (WorkspaceError, OSError) as e:
            console.print(f"   ❌ Failed to remove workspace for {dev_name}: {e}")
            return False
    
    def list_workspaces(self) -> List[str]:
        """List all workspace directories for the current project.
        
        Returns:
            List of dev environment names with workspaces
        """
        workspaces = []
        project_prefix = f"{self.project.info.name}-"
        
        workspaces_dir = self.get_workspace_dir("").parent  # Get parent to list all workspaces
        if not workspaces_dir.exists():
            return workspaces
        
        try:
            for workspace_dir in workspaces_dir.iterdir():
                if (workspace_dir.is_dir() and 
                    workspace_dir.name.startswith(project_prefix) and
                    not is_directory_empty(workspace_dir)):
                    
                    dev_name = workspace_dir.name[len(project_prefix):]
                    workspaces.append(dev_name)
            
            return sorted(workspaces)
            
        except OSError:
            return workspaces
    
    def cleanup_unused_workspaces(self, active_dev_names: Set[str]) -> int:
        """Clean up workspace directories that are no longer in use.
        
        Args:
            active_dev_names: Set of currently active dev environment names
            
        Returns:
            Number of workspaces cleaned up
        """
        all_workspaces = set(self.list_workspaces())
        unused_workspaces = all_workspaces - active_dev_names
        
        cleaned_count = 0
        for dev_name in unused_workspaces:
            if self.remove_workspace(dev_name):
                cleaned_count += 1
        
        return cleaned_count
    
    def cleanup_unused_workspaces_all_projects(self, docker_client) -> int:
        """Clean up workspace directories across all projects that are no longer in use.
        
        Args:
            docker_client: DockerClient instance to check for active containers
            
        Returns:
            Number of workspaces cleaned up
        """
        from ..utils.docker_client import DockerError
        
        workspaces_dir = self.get_workspace_dir("").parent  # Get parent to list all workspaces
        if not workspaces_dir.exists():
            return 0
        
        cleaned_count = 0
        
        try:
            # Get all active containers with devs labels across all projects
            active_containers = docker_client.find_containers_by_labels({"devs.managed": "true"})
            active_workspaces = set()
            
            # Build set of active workspace names from running containers
            for container in active_containers:
                if container['status'].lower() == 'running':
                    project_name = container['labels'].get('devs.project', '')
                    dev_name = container['labels'].get('devs.dev', '')
                    if project_name and dev_name:
                        workspace_name = f"{project_name}-{dev_name}"
                        active_workspaces.add(workspace_name)
            
            # Check all workspace directories
            for workspace_dir in workspaces_dir.iterdir():
                if workspace_dir.is_dir() and not workspace_dir.name.startswith('.'):
                    workspace_name = workspace_dir.name
                    
                    # If this workspace doesn't have a corresponding running container, remove it
                    if workspace_name not in active_workspaces:
                        try:
                            console.print(f"   🗑️  Removed workspace: {workspace_dir}")
                            shutil.rmtree(workspace_dir)
                            cleaned_count += 1
                        except OSError as e:
                            console.print(f"   ❌ Failed to remove workspace {workspace_dir}: {e}")
                            continue
            
            return cleaned_count
            
        except (OSError, DockerError) as e:
            console.print(f"❌ Error during cross-project workspace cleanup: {e}")
            return 0
    
    def sync_workspace(self, dev_name: str, files_to_sync: Optional[List[str]] = None) -> bool:
        """Sync specific files from project to workspace.
        
        Args:
            dev_name: Development environment name
            files_to_sync: List of files to sync, or None for git-tracked files
            
        Returns:
            True if sync was successful
        """
        workspace_dir = self.get_workspace_dir(dev_name)
        
        if not self.workspace_exists(dev_name):
            console.print(f"   ❌ Workspace for {dev_name} does not exist")
            return False
        
        try:
            if files_to_sync is None:
                # Sync git-tracked files
                if self.project.info.is_git_repo:
                    tracked_files = get_tracked_files(self.project.project_dir)
                    copy_file_list(
                        source_dir=self.project.project_dir,
                        dest_dir=workspace_dir,
                        file_list=tracked_files,
                        preserve_permissions=True
                    )
                else:
                    console.print(f"   ⚠️  Not a git repository, cannot sync tracked files")
                    return False
            else:
                # Sync specific files
                file_paths = [self.project.project_dir / f for f in files_to_sync]
                copy_file_list(
                    source_dir=self.project.project_dir,
                    dest_dir=workspace_dir,
                    file_list=file_paths,
                    preserve_permissions=True
                )
            
            console.print(f"   ✅ Synced workspace for {dev_name}")
            return True
            
        except Exception as e:
            console.print(f"   ❌ Failed to sync workspace for {dev_name}: {e}")
            return False