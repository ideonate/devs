"""DevContainer CLI wrapper utilities."""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..exceptions import DevsError, DependencyError


class DevContainerCLI:
    """Wrapper for DevContainer CLI operations."""
    
    def __init__(self) -> None:
        """Initialize DevContainer CLI wrapper."""
        self._check_devcontainer_cli()
    
    def _check_devcontainer_cli(self) -> None:
        """Check if devcontainer CLI is available.
        
        Raises:
            DependencyError: If devcontainer CLI is not found
        """
        try:
            result = subprocess.run(
                ['devcontainer', '--version'], 
                capture_output=True, 
                text=True,
                check=False
            )
            if result.returncode != 0:
                raise DependencyError(
                    "DevContainer CLI not found. Install with: npm install -g @devcontainers/cli"
                )
        except FileNotFoundError:
            raise DependencyError(
                "DevContainer CLI not found. Install with: npm install -g @devcontainers/cli"
            )
    
    def up(
        self,
        workspace_folder: Path,
        dev_name: str,
        project_name: str,
        git_remote_url: str = "",
        rebuild: bool = False,
        remove_existing: bool = True
    ) -> bool:
        """Start a devcontainer.
        
        Args:
            workspace_folder: Path to workspace folder
            dev_name: Development environment name
            project_name: Project name for labeling
            git_remote_url: Git remote URL
            rebuild: Whether to rebuild the image
            remove_existing: Whether to remove existing container
            
        Returns:
            True if successful
            
        Raises:
            DevsError: If devcontainer up fails
        """
        try:
            cmd = ['devcontainer', 'up', '--workspace-folder', str(workspace_folder)]
            
            # Add rebuild flag if requested
            if rebuild:
                cmd.append('--build-no-cache')
            
            # Add remove existing flag
            if remove_existing:
                cmd.append('--remove-existing-container')
            
            # Add ID labels for identification
            cmd.extend([
                '--id-label', f'devs.project={project_name}',
                '--id-label', f'devs.dev={dev_name}',
            ])
            
            # Set environment variables
            env = os.environ.copy()
            env.update({
                'DEVCONTAINER_NAME': dev_name,
                'GIT_REMOTE_URL': git_remote_url,
                'WORKSPACE_FOLDER_NAME': f"{workspace_folder.name}",
            })
            
            result = subprocess.run(
                cmd,
                cwd=workspace_folder,
                env=env,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise DevsError(f"DevContainer up failed: {result.stderr}")
            
            return True
            
        except subprocess.SubprocessError as e:
            raise DevsError(f"DevContainer CLI execution failed: {e}")
    
    def exec_command(
        self,
        workspace_folder: Path,
        command: List[str],
        workdir: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Execute a command in the devcontainer.
        
        Args:
            workspace_folder: Path to workspace folder
            command: Command to execute
            workdir: Working directory for command
            
        Returns:
            Completed process result
            
        Raises:
            DevsError: If command execution fails
        """
        try:
            cmd = ['devcontainer', 'exec', '--workspace-folder', str(workspace_folder)]
            
            if workdir:
                cmd.extend(['--workdir', workdir])
            
            cmd.append('--')
            cmd.extend(command)
            
            result = subprocess.run(
                cmd,
                cwd=workspace_folder,
                capture_output=True,
                text=True,
                check=False
            )
            
            return result
            
        except subprocess.SubprocessError as e:
            raise DevsError(f"DevContainer exec failed: {e}")
    
    def stop(self, workspace_folder: Path) -> bool:
        """Stop a devcontainer.
        
        Args:
            workspace_folder: Path to workspace folder
            
        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                ['devcontainer', 'stop', '--workspace-folder', str(workspace_folder)],
                capture_output=True,
                text=True,
                check=False
            )
            
            return result.returncode == 0
            
        except subprocess.SubprocessError:
            return False
    
    def get_container_id(self, workspace_folder: Path) -> Optional[str]:
        """Get the container ID for a workspace.
        
        Args:
            workspace_folder: Path to workspace folder
            
        Returns:
            Container ID if found, None otherwise
        """
        try:
            result = subprocess.run(
                ['devcontainer', 'exec', '--workspace-folder', str(workspace_folder), 
                 '--', 'hostname'],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            
            return None
            
        except subprocess.SubprocessError:
            return None