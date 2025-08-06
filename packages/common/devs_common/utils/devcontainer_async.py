"""Async DevContainer CLI wrapper utilities."""

import asyncio
import os
from pathlib import Path
from typing import List, Optional, Tuple

from ..exceptions import DevsError, DependencyError
from ..config import BaseConfig


class AsyncDevContainerCLI:
    """Async wrapper for DevContainer CLI operations."""
    
    def __init__(self, config: Optional[BaseConfig] = None) -> None:
        """Initialize Async DevContainer CLI wrapper.
        Args:
            config: Optional config object for container labels
        """
        self.config = config
    
    async def check_devcontainer_cli(self) -> bool:
        """Check if devcontainer CLI is available.
        
        Returns:
            True if available
            
        Raises:
            DependencyError: If devcontainer CLI is not found
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "devcontainer", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode != 0:
                raise DependencyError(
                    "DevContainer CLI not found. Install with: npm install -g @devcontainers/cli"
                )
            return True
        except FileNotFoundError:
            raise DependencyError(
                "DevContainer CLI not found. Install with: npm install -g @devcontainers/cli"
            )
    
    async def up(
        self,
        workspace_folder: Path,
        dev_name: str,
        project_name: str,
        git_remote_url: str = "",
        rebuild: bool = False,
        remove_existing: bool = True,
        debug: bool = False,
        config_path: Optional[Path] = None
    ) -> bool:
        """Start a devcontainer asynchronously.
        
        Args:
            workspace_folder: Path to workspace folder
            dev_name: Development environment name
            project_name: Project name for labeling
            git_remote_url: Git remote URL
            rebuild: Whether to rebuild the image
            remove_existing: Whether to remove existing container
            debug: Whether to show debug output
            config_path: Optional path to external devcontainer config directory
            
        Returns:
            True if successful
            
        Raises:
            DevsError: If devcontainer up fails
        """
        try:
            cmd = ["devcontainer", "up", "--workspace-folder", str(workspace_folder)]
            
            # Add config path if provided
            if config_path:
                cmd.extend(["--config", str(config_path)])
            
            # Add rebuild flag if requested
            if rebuild:
                cmd.append("--build-no-cache")
            
            # Add remove existing flag
            if remove_existing:
                cmd.append("--remove-existing-container")
            
            # Add ID labels for identification
            cmd.extend([
                "--id-label", f"devs.project={project_name}",
                "--id-label", f"devs.dev={dev_name}",
            ])
            
            # Add extra container labels from config if provided
            if self.config and hasattr(self.config, 'container_labels'):
                for k, v in self.config.container_labels.items():
                    if k not in ('devs.project', 'devs.dev'):
                        cmd.extend(["--id-label", f"{k}={v}"])
            
            # Set environment variables
            env = os.environ.copy()
            env.update({
                "DEVCONTAINER_NAME": dev_name,
                "GIT_REMOTE_URL": git_remote_url,
                "WORKSPACE_FOLDER_NAME": f"{workspace_folder.name}",
            })
            
            # Set environment mount path
            env_mount_path = Path.home() / '.devs' / 'envs' / project_name
            if not env_mount_path.exists():
                env_mount_path = Path.home() / '.devs' / 'envs' / 'default'
                env_mount_path.mkdir(parents=True, exist_ok=True)
            
            env['DEVS_ENV_MOUNT_PATH'] = str(env_mount_path)
            
            # Pass debug mode to container scripts
            if debug:
                env['DEVS_DEBUG'] = 'true'
            
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_folder,
                env=env
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=600.0  # 10 minutes timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise DevsError("DevContainer up timed out after 10 minutes")
            
            if process.returncode != 0:
                error_msg = f"DevContainer up failed (exit code {process.returncode})"
                if stderr:
                    error_msg += f": {stderr.decode('utf-8')}"
                raise DevsError(error_msg)
            
            return True
            
        except Exception as e:
            if isinstance(e, DevsError):
                raise
            raise DevsError(f"DevContainer CLI execution failed: {e}")
    
    async def exec_command(
        self,
        workspace_folder: Path,
        command: List[str],
        workdir: Optional[str] = None,
        timeout: float = 120.0
    ) -> Tuple[bool, str, str]:
        """Execute a command in the devcontainer asynchronously.
        
        Args:
            workspace_folder: Path to workspace folder
            command: Command to execute
            workdir: Working directory for command
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
            
        Raises:
            DevsError: If command execution fails
        """
        try:
            cmd = ["devcontainer", "exec", "--workspace-folder", str(workspace_folder)]
            
            if workdir:
                cmd.extend(["--workdir", workdir])
            
            cmd.append("--")
            cmd.extend(command)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_folder
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, "", f"Command timed out after {timeout} seconds"
            
            return (
                process.returncode == 0,
                stdout.decode('utf-8', errors='replace') if stdout else "",
                stderr.decode('utf-8', errors='replace') if stderr else ""
            )
            
        except Exception as e:
            return False, "", str(e)
    
    async def stop(self, workspace_folder: Path) -> bool:
        """Stop a devcontainer asynchronously.
        
        Args:
            workspace_folder: Path to workspace folder
            
        Returns:
            True if successful
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "devcontainer", "stop", "--workspace-folder", str(workspace_folder),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await asyncio.wait_for(
                process.communicate(),
                timeout=30.0
            )
            
            return process.returncode == 0
            
        except (asyncio.TimeoutError, Exception):
            return False
    
    async def get_container_id(self, workspace_folder: Path) -> Optional[str]:
        """Get the container ID for a workspace asynchronously.
        
        Args:
            workspace_folder: Path to workspace folder
            
        Returns:
            Container ID if found, None otherwise
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "devcontainer", "exec", "--workspace-folder", str(workspace_folder), 
                "--", "hostname",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
            
            if process.returncode == 0 and stdout:
                return stdout.decode('utf-8').strip()
            
            return None
            
        except (asyncio.TimeoutError, Exception):
            return None