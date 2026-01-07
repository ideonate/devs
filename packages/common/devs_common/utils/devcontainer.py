"""DevContainer CLI wrapper utilities."""

import os
import re
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ..exceptions import DevsError, DependencyError, PortConflictError
from ..config import BaseConfig
from .console import get_console
from .config_hash import get_env_mount_path

# Initialize console based on environment
console = get_console()


def prepare_devcontainer_environment(
    dev_name: str,
    project_name: str,
    workspace_folder: Path,
    container_workspace_name: str,
    git_remote_url: str = "",
    debug: bool = False,
    live: bool = False,
    extra_env: Optional[dict] = None
) -> dict:
    """Prepare environment variables for devcontainer operations.
    
    Args:
        dev_name: Development environment name
        project_name: Project name for environment paths
        workspace_folder: Path to workspace folder on host
        container_workspace_name: Name of workspace folder in container
        git_remote_url: Git remote URL (optional)
        debug: Whether debug mode is enabled
        live: Whether to use live mode (mount current directory)
        extra_env: Additional environment variables to pass to container
        
    Returns:
        Dictionary of environment variables
    """
    env = os.environ.copy()
    
    # Core devcontainer environment variables
    # IMPORTANT: In live mode, we must use the actual host folder name (e.g. "workstuff")
    # instead of our constructed name (e.g. "workstuffai-workstuffapp-dan") because
    # the devcontainer CLI directly mounts the host folder and preserves its name.
    # The container will have /workspaces/<host-folder-name>, not /workspaces/<constructed-name>
    workspace_folder_name = workspace_folder.name if live else container_workspace_name
    
    env.update({
        'DEVCONTAINER_NAME': dev_name,
        'GIT_REMOTE_URL': git_remote_url,
        'WORKSPACE_FOLDER_NAME': workspace_folder_name,
    })
    
    # Set environment mount path (uses project-specific if exists, else default)
    env_mount_path = get_env_mount_path(project_name)

    # Ensure the directory exists and has a basic .env file
    env_mount_path.mkdir(parents=True, exist_ok=True)
    env_file = env_mount_path / '.env'
    if not env_file.exists():
        # Create default .env file with GH_TOKEN if available
        env_content = ""
        if 'GH_TOKEN' in os.environ:
            env_content = f"GH_TOKEN={os.environ['GH_TOKEN']}\n"
        env_file.write_text(env_content)

    env['DEVS_ENV_MOUNT_PATH'] = str(env_mount_path)
    
    # Set bridge mount path
    bridge_mount_path = Path.home() / '.devs' / 'bridge' / f"{project_name}-{dev_name}"
    bridge_mount_path.mkdir(parents=True, exist_ok=True)
    env['DEVS_BRIDGE_MOUNT_PATH'] = str(bridge_mount_path)
    
    # Pass debug mode to container scripts
    if debug:
        env['DEVS_DEBUG'] = 'true'
    
    # Pass live mode to container scripts
    if live:
        env['DEVS_LIVE_MODE'] = 'true'
    
    # Pass through GH_TOKEN if available (for GitHub authentication)
    if 'GH_TOKEN' in os.environ:
        env['GH_TOKEN'] = os.environ['GH_TOKEN']
    
    # Merge in any extra environment variables
    if extra_env:
        env.update(extra_env)

    return env


def parse_docker_error(error_output: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse Docker error output for specific error patterns.

    Args:
        error_output: The stderr/stdout from Docker or devcontainer command

    Returns:
        Tuple of (error_type, details) where:
        - error_type: 'port_conflict', 'daemon_not_running', or None
        - details: Additional info (e.g., port number for port conflicts)
    """
    # Check for port conflict errors
    # Pattern: "Bind for 0.0.0.0:5002 failed: port is already allocated"
    # Also handles IPv6: "Bind for [::]:3000 failed: port is already allocated"
    port_conflict_pattern = r'Bind for (?:[^:]+|\[.*?\]):(\d+) failed: port is already allocated'
    port_match = re.search(port_conflict_pattern, error_output)
    if port_match:
        return ('port_conflict', port_match.group(1))

    # Check for Docker daemon not running
    if 'Cannot connect to the Docker daemon' in error_output:
        return ('daemon_not_running', None)

    # Check for image pull errors
    if 'pull access denied' in error_output.lower() or 'not found' in error_output.lower():
        image_pattern = r'(?:pull access denied for|repository does not exist)[^:]*:?\s*([^\s,]+)'
        image_match = re.search(image_pattern, error_output, re.IGNORECASE)
        if image_match:
            return ('image_not_found', image_match.group(1))

    return (None, None)


def format_port_conflict_error(port: str) -> str:
    """Format a user-friendly error message for port conflicts.

    Args:
        port: The port number that is conflicting

    Returns:
        Formatted error message with actionable suggestions
    """
    return f"""Port {port} is already in use by another process

To resolve this:
• Find and stop the process using port {port}:
  lsof -ti:{port} | xargs ps -p
  lsof -ti:{port} | xargs kill -9
• Or stop other devcontainers that may be using this port:
  devs list
  devs stop <container-name>"""


class DevContainerCLI:
    """Wrapper for DevContainer CLI operations."""
    
    def __init__(self, config: Optional[BaseConfig] = None) -> None:
        """Initialize DevContainer CLI wrapper.
        Args:
            config: Optional config object for container labels
        """
        self._check_devcontainer_cli()
        self.config = config
    
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
    
    def _check_github_token_setup(self, env_mount_path: Path) -> None:
        """Check if GH_TOKEN is properly configured and warn if missing.
        
        Args:
            env_mount_path: Path to the environment directory containing .env file
        """
        env_file = env_mount_path / '.env'
        
        # Check if GH_TOKEN is in environment or .env file
        has_env_token = 'GH_TOKEN' in os.environ and os.environ['GH_TOKEN'].strip()
        has_file_token = False
        
        if env_file.exists():
            try:
                env_content = env_file.read_text()
                # Simple check for GH_TOKEN=something (non-empty)
                for line in env_content.splitlines():
                    line = line.strip()
                    if line.startswith('GH_TOKEN=') and len(line) > len('GH_TOKEN='):
                        has_file_token = True
                        break
            except Exception:
                # If we can't read the file, continue without error
                pass
        
        if not has_env_token and not has_file_token:
            console.print()
            console.print("⚠️  [bold yellow]GitHub Token Not Configured[/bold yellow]")
            console.print("   GitHub operations (private repos, API access) may fail.")
            console.print()
            console.print("   [bold]To fix this:[/bold]")
            console.print(f"   1. Set environment variable: [cyan]export GH_TOKEN=your_token_here[/cyan]")
            console.print(f"   2. Or add to file: [cyan]{env_file}[/cyan]")
            console.print("      [dim]GH_TOKEN=your_token_here[/dim]")
            console.print()
            console.print("   Get a token at: [link]https://github.com/settings/tokens[/link]")
            console.print()

    def up(
        self,
        workspace_folder: Path,
        dev_name: str,
        project_name: str,
        container_workspace_name: str,
        git_remote_url: str = "",
        rebuild: bool = False,
        remove_existing: bool = True,
        debug: bool = False,
        config_path: Optional[Path] = None,
        live: bool = False,
        extra_env: Optional[dict] = None,
        config_hash: Optional[str] = None
    ) -> bool:
        """Start a devcontainer.
        
        Args:
            workspace_folder: Path to workspace folder on host
            dev_name: Development environment name
            project_name: Project name for labeling
            container_workspace_name: Name of workspace folder in container
            git_remote_url: Git remote URL
            rebuild: Whether to rebuild the image
            remove_existing: Whether to remove existing container
            debug: Whether to show debug output
            config_path: Optional path to external devcontainer config directory
            live: Whether to use live mode (mount current directory)
            extra_env: Additional environment variables to pass to container
            config_hash: Optional hash of config files for detecting changes

        Returns:
            True if successful
            
        Raises:
            DevsError: If devcontainer up fails
        """
        try:
            cmd = ['devcontainer', 'up', '--workspace-folder', str(workspace_folder)]
            
            # Add config path if provided (use external config instead of copying to workspace)
            if config_path:
                cmd.extend(['--config', str(config_path)])
            
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
            
            # Add live mode label if applicable
            if live:
                cmd.extend(['--id-label', 'devs.live=true'])

            # Add config hash label for detecting config changes
            if config_hash:
                cmd.extend(['--id-label', f'devs.config-hash={config_hash}'])

            # Add extra container labels from config if provided
            if self.config and hasattr(self.config, 'container_labels'):
                for k, v in self.config.container_labels.items():
                    if k not in ('devs.project', 'devs.dev', 'devs.live'):
                        cmd.extend(['--id-label', f'{k}={v}'])
            
            # Set environment variables using shared function
            env = prepare_devcontainer_environment(
                dev_name=dev_name,
                project_name=project_name,
                workspace_folder=workspace_folder,
                container_workspace_name=container_workspace_name,
                git_remote_url=git_remote_url,
                debug=debug,
                live=live,
                extra_env=extra_env
            )
            
            # Check if GH_TOKEN is configured and warn if missing
            env_mount_path = Path(env['DEVS_ENV_MOUNT_PATH'])
            self._check_github_token_setup(env_mount_path)
            
            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
                console.print(f"[dim]Environment variables: DEVCONTAINER_NAME={env.get('DEVCONTAINER_NAME')}, GIT_REMOTE_URL={env.get('GIT_REMOTE_URL')}, GH_TOKEN={'***' if env.get('GH_TOKEN') else 'not set'}, DEVS_DEBUG={env.get('DEVS_DEBUG', 'not set')}[/dim]")
                
                if extra_env:
                    console.print(f"[dim]🔧 Extra variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}[/dim]")

            if debug:
                # In debug mode, stream output in real-time
                result = subprocess.run(
                    cmd,
                    cwd=workspace_folder,
                    env=env,
                    text=True,
                    check=False
                )
            else:
                # In normal mode, capture output for error handling
                result = subprocess.run(
                    cmd,
                    cwd=workspace_folder,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False
                )

            if result.returncode == 0:
                if debug:
                    console.print("[dim]DevContainer up completed successfully[/dim]")
                else:
                    # Log successful output for troubleshooting
                    console.print(f"   ✅ DevContainer up completed successfully")
                    if result.stdout:
                        # Show post-create script output (last 30 lines)
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 30:
                            console.print(f"   [dim]... ({len(lines) - 30} lines truncated)[/dim]")
                            lines = lines[-30:]
                        for line in lines:
                            console.print(f"   [dim]{line}[/dim]")
            else:
                # Combine stderr and stdout for error parsing
                full_output = (result.stderr or '') + (result.stdout or '')

                # Parse for specific Docker errors
                error_type, error_details = parse_docker_error(full_output)

                if error_type == 'port_conflict' and error_details:
                    # Provide user-friendly port conflict message
                    console.print(f"   [bold red]Port {error_details} is already in use by another process[/bold red]")
                    console.print()
                    console.print("   [bold]To resolve this:[/bold]")
                    console.print(f"   • Find and stop the process using port {error_details}:")
                    console.print(f"     [cyan]lsof -ti:{error_details} | xargs ps -p[/cyan]")
                    console.print(f"     [cyan]lsof -ti:{error_details} | xargs kill -9[/cyan]")
                    console.print("   • Or stop other devcontainers that may be using this port:")
                    console.print("     [cyan]devs list[/cyan]")
                    console.print("     [cyan]devs stop <container-name>[/cyan]")
                    raise PortConflictError(error_details)

                elif error_type == 'daemon_not_running':
                    console.print("   [bold red]Docker daemon is not running[/bold red]")
                    console.print()
                    console.print("   [bold]To resolve this:[/bold]")
                    console.print("   • Start Docker Desktop (macOS/Windows)")
                    console.print("   • Or start the Docker service: [cyan]sudo systemctl start docker[/cyan]")
                    raise DevsError("Docker daemon is not running")

                else:
                    # Generic error handling
                    error_msg = f"DevContainer up failed (exit code {result.returncode})"
                    if result.stderr:
                        error_msg += f": {result.stderr}"
                    if result.stdout:
                        console.print(f"   [yellow]DevContainer stdout:[/yellow]")
                        for line in result.stdout.strip().split('\n')[-50:]:
                            console.print(f"   {line}")
                    raise DevsError(error_msg)
            
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