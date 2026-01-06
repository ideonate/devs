"""Container management and lifecycle operations."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess

from ..config import BaseConfig


def _parse_docker_timestamp(timestamp: str) -> datetime:
    """Parse Docker timestamp which may have nanosecond precision.

    Docker on Linux can return timestamps with 9 decimal places (nanoseconds),
    but Python's fromisoformat() only handles up to 6 (microseconds).

    Args:
        timestamp: ISO format timestamp string from Docker

    Returns:
        datetime object
    """
    # Replace Z with +00:00 for timezone handling
    timestamp = timestamp.replace('Z', '+00:00')

    # Truncate nanoseconds to microseconds if present
    # Match pattern: digits after decimal point before timezone
    match = re.match(r'(.+\.\d{6})\d*([+-]\d{2}:\d{2})$', timestamp)
    if match:
        timestamp = match.group(1) + match.group(2)

    return datetime.fromisoformat(timestamp)


from ..exceptions import ContainerError, DockerError
from ..utils.docker_client import DockerClient
from ..utils.devcontainer import DevContainerCLI
from ..utils.devcontainer_template import get_template_dir
from ..utils.console import get_console
from ..utils.config_hash import compute_env_config_hash, get_env_mount_path
from .project import Project

# Initialize console based on environment
console = get_console()


class ContainerInfo:
    """Information about a devcontainer."""
    
    def __init__(
        self,
        name: str,
        dev_name: str,
        project_name: str,
        status: str,
        container_id: str = "",
        created: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        self.name = name
        self.dev_name = dev_name
        self.project_name = project_name
        self.status = status
        self.container_id = container_id
        self.created = created
        self.labels = labels or {}


class ContainerManager:
    """Manages Docker containers for devcontainer environments."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize container manager.
        
        Args:
            project: Project instance
            config: Configuration instance (optional)
        """
        self.project = project
        self.config = config
        self.docker = DockerClient()
        self.devcontainer = DevContainerCLI(config)
    
    def _get_container_info(self, dev_name: str, live: bool = False) -> Dict[str, str]:
        """Get container names and paths for a dev environment.
        
        Args:
            dev_name: Development environment name
            live: Whether container is in live mode
            
        Returns:
            Dictionary with container_name, workspace_name, container_workspace_dir
        """
        project_prefix = self.config.project_prefix if self.config else "dev"
        container_name = self.project.get_container_name(dev_name, project_prefix)
        
        # In live mode, workspace name is determined differently
        if live:
            # This would need workspace_dir parameter to get workspace_dir.name
            # For now, keep it simple and let callers handle live mode logic
            workspace_name = self.project.get_workspace_name(dev_name)
        else:
            workspace_name = self.project.get_workspace_name(dev_name)
        
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        return {
            "container_name": container_name,
            "workspace_name": workspace_name, 
            "container_workspace_dir": container_workspace_dir
        }
    
    def _get_project_labels(self, dev_name: str, live: bool = False) -> Dict[str, str]:
        """Get standard project labels for container operations.
        
        Args:
            dev_name: Development environment name
            live: Whether container is in live mode
            
        Returns:
            Dictionary of labels
        """
        labels = {
            "devs.project": self.project.info.name,
            "devs.dev": dev_name,
        }
        
        # Add live mode label if applicable
        if live:
            labels["devs.live"] = "true"
        
        # Add config labels if available
        if self.config:
            labels.update(self.config.container_labels)
        
        return labels
    
    def should_rebuild_image(self, dev_name: str) -> Tuple[bool, str]:
        """Check if devcontainer image should be rebuilt.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Tuple of (should_rebuild, reason)
        """
        try:
            # Find existing images for this devcontainer configuration
            image_pattern = f"vsc-{self.project.get_workspace_name(dev_name)}-"
            existing_images = self.docker.find_images_by_pattern(image_pattern)
            
            if not existing_images:
                return False, "No existing image found"
            
            # Get the newest image creation time
            newest_image_time = None
            for image_name in existing_images:
                image_time = self.docker.get_image_creation_time(image_name)
                if image_time and (not newest_image_time or image_time > newest_image_time):
                    newest_image_time = image_time
            
            if not newest_image_time:
                return False, "Could not determine image age"
            
            # Check if devcontainer-related files are newer than the image
            devcontainer_files = [
                self.project.project_dir / ".devcontainer",
                self.project.project_dir / "Dockerfile", 
                self.project.project_dir / "docker-compose.yml",
                self.project.project_dir / "docker-compose.yaml",
            ]
            
            for file_path in devcontainer_files:
                if file_path.exists():
                    if file_path.is_file():
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                        if file_time > newest_image_time:
                            return True, f"File newer than image: {file_path.name}"
                    elif file_path.is_dir():
                        # For directories, find the newest file
                        newest_file_time = None
                        newest_file = None
                        
                        for item in file_path.rglob('*'):
                            if item.is_file():
                                item_time = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                                if not newest_file_time or item_time > newest_file_time:
                                    newest_file_time = item_time
                                    newest_file = item
                        
                        if newest_file_time and newest_file_time > newest_image_time:
                            return True, f"File newer than image: {newest_file}"
            
            return False, "Image is up to date"
            
        except (DockerError, OSError) as e:
            console.print(f"[yellow]Warning: Could not check image rebuild status: {e}[/yellow]")
            return False, "Could not determine rebuild status"
    
    def ensure_container_running(
        self, 
        dev_name: str,
        workspace_dir: Path,
        force_rebuild: bool = False,
        debug: bool = False,
        live: bool = False,
        extra_env: Optional[Dict[str, str]] = None
    ) -> bool:
        """Ensure a container is running for the specified dev environment.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            force_rebuild: Force rebuild even if not needed
            debug: Show debug output for devcontainer operations
            live: Whether to use live mode (mount current directory instead of copying)
            extra_env: Additional environment variables to pass to container
            
        Returns:
            True if container is running successfully
            
        Raises:
            ContainerError: If container operations fail
        """
        workspace_info = self._get_container_info(dev_name, live)
        container_name = workspace_info["container_name"]
        project_labels = self._get_project_labels(dev_name, live)
        
        try:
            # Check if we need to rebuild
            rebuild_needed, rebuild_reason = self.should_rebuild_image(dev_name)
            if rebuild_needed or force_rebuild:
                if force_rebuild:
                    console.print(f"   🔄 Forcing image rebuild for {dev_name}...")
                else:
                    console.print(f"   🔄 {rebuild_reason}, rebuilding image...")
                
                # Stop existing container if running
                existing_containers = self.docker.find_containers_by_labels(project_labels)
                for existing_container in existing_containers:
                    if debug:
                        console.print(f"[dim]Stopping container: {existing_container['name']}[/dim]")
                    self.docker.stop_container(existing_container['name'])
                    if debug:
                        console.print(f"[dim]Removing container: {existing_container['name']}[/dim]")
                    self.docker.remove_container(existing_container['name'])
            
            # Compute current config hash for comparison
            env_mount_path = get_env_mount_path(self.project.info.name)
            current_config_hash = compute_env_config_hash(self.project.info.name)
            console.print(f"   📁 Env mount: {env_mount_path} (hash: {current_config_hash})")

            # Check if container is already running
            if debug:
                console.print(f"[dim]Checking for existing containers with labels: {project_labels}[/dim]")
            existing_containers = self.docker.find_containers_by_labels(project_labels)
            config_hash_changed = False

            if existing_containers and not (rebuild_needed or force_rebuild):
                existing_container = existing_containers[0]
                existing_labels = existing_container.get('labels', {})
                existing_is_live = existing_labels.get('devs.live') == 'true'
                existing_config_hash = existing_labels.get('devs.config-hash', '')

                console.print(f"   🔍 Found container: {existing_container['name']} (status: {existing_container['status']}, hash: {existing_config_hash or 'none'})")

                # Check if config hash has changed
                if existing_config_hash and existing_config_hash != current_config_hash:
                    config_hash_changed = True
                    console.print(f"   🔄 Config hash changed ({existing_config_hash} → {current_config_hash}), will restart container")
                elif not existing_config_hash:
                    console.print(f"   ⚠️  Container has no config hash label, will restart to add it")
                    config_hash_changed = True

                # Check if existing container matches the requested mode
                if existing_is_live != live:
                    mode_str = "live" if live else "workspace copy"
                    existing_mode_str = "live" if existing_is_live else "workspace copy"
                    raise ContainerError(
                        f"Container {dev_name} already exists in {existing_mode_str} mode, "
                        f"but {mode_str} mode was requested. Stop the container first with: devs stop {dev_name}"
                    )

                if existing_container['status'] == 'running' and not config_hash_changed:
                    console.print(f"   ✅ Container already running with matching config, reusing")
                    return True
                elif config_hash_changed:
                    # Config changed, need to restart container
                    console.print(f"   🛑 Stopping container for restart...")
                    self.docker.stop_container(existing_container['name'])
                    self.docker.remove_container(existing_container['name'], force=True)
                else:
                    # Container exists but not running, remove it
                    console.print(f"   🗑️  Container exists but not running, removing...")
                    self.docker.remove_container(existing_container['name'], force=True)
            else:
                if rebuild_needed or force_rebuild:
                    console.print(f"   🔨 Rebuild needed (devcontainer files changed or force_rebuild)")
                else:
                    console.print(f"   📦 No existing container found, will create new one")
            
            console.print(f"   🚀 Starting container for {dev_name}...")
            
            # Determine config path based on whether .devcontainer was copied to workspace
            config_path = None
            workspace_devcontainer = workspace_dir / ".devcontainer"
            project_devcontainer = self.project.project_dir / ".devcontainer"
            
            if workspace_devcontainer.exists():
                # .devcontainer was copied to workspace, use it (config_path = None)
                config_path = None
            elif project_devcontainer.exists():
                # .devcontainer exists in project but not copied (gitignored), use original
                config_path = project_devcontainer / "devcontainer.json"
            else:
                # No .devcontainer in project, use devs template
                config_path = get_template_dir() / "devcontainer.json"
            
            # Start devcontainer
            container_workspace_name = workspace_info["workspace_name"]
            success = self.devcontainer.up(
                workspace_folder=workspace_dir,
                dev_name=dev_name,
                project_name=self.project.info.name,
                container_workspace_name=container_workspace_name,
                git_remote_url=self.project.info.git_remote_url,
                rebuild=rebuild_needed or force_rebuild,
                remove_existing=True,
                debug=debug,
                config_path=config_path,
                live=live,
                extra_env=extra_env,
                config_hash=current_config_hash
            )
            
            if not success:
                raise ContainerError(f"Failed to start devcontainer for {dev_name}")
            
            # Get the created container and verify it's healthy
            if debug:
                console.print(f"[dim]Looking for created containers with labels: {project_labels}[/dim]")
            created_containers = self.docker.find_containers_by_labels(project_labels)
            if not created_containers:
                raise ContainerError(f"No container found after devcontainer up for {dev_name}")
            
            created_container = created_containers[0]
            container_name_actual = created_container['name']
            
            if debug:
                console.print(f"[dim]Found created container: {container_name_actual}[/dim]")
            
            # Test container health
            console.print(f"   🔍 Checking container health for {dev_name}...")
            if debug:
                console.print(f"[dim]Running health check: docker exec {container_name_actual} echo 'Container ready'[/dim]")
            if not self.docker.exec_command(container_name_actual, "echo 'Container ready'"):
                raise ContainerError(f"Container {dev_name} is not responding")
            
            # Rename container if needed
            if container_name_actual != container_name:
                try:
                    if debug:
                        console.print(f"[dim]Renaming container from {container_name_actual} to {container_name}[/dim]")
                    self.docker.rename_container(container_name_actual, container_name)
                except DockerError:
                    console.print(f"   ⚠️  Could not rename container to {container_name}")
            
            console.print(f"   ✅ Started: {dev_name}")
            return True
            
        except (DockerError, ContainerError) as e:
            # Clean up any failed containers
            try:
                failed_containers = self.docker.find_containers_by_labels(project_labels)
                for container_info in failed_containers:
                    self.docker.stop_container(container_info['name'])
                    self.docker.remove_container(container_info['name'])
            except DockerError:
                pass
            
            raise ContainerError(f"Failed to ensure container running for {dev_name}: {e}")
    
    def stop_container(self, dev_name: str) -> bool:
        """Stop and remove a container by labels (more reliable than names).
        
        Args:
            dev_name: Development environment name
            
        Returns:
            True if container was stopped/removed
        """
        project_labels = self._get_project_labels(dev_name)
        
        try:
            console.print(f"   🔍 Looking for containers with labels: {project_labels}")
            existing_containers = self.docker.find_containers_by_labels(project_labels)
            console.print(f"   📋 Found {len(existing_containers)} containers")
            
            if existing_containers:
                for container_info in existing_containers:
                    container_name = container_info['name']
                    container_status = container_info['status']
                    
                    console.print(f"   🛑 Stopping container: {container_name} (status: {container_status})")
                    try:
                        stop_result = self.docker.stop_container(container_name)
                        console.print(f"   📋 Stop result: {stop_result}")
                    except DockerError as stop_e:
                        console.print(f"   ⚠️  Stop failed for {container_name}: {stop_e}")
                    
                    console.print(f"   🗑️  Removing container: {container_name}")
                    try:
                        remove_result = self.docker.remove_container(container_name)
                        console.print(f"   📋 Remove result: {remove_result}")
                    except DockerError as remove_e:
                        console.print(f"   ⚠️  Remove failed for {container_name}: {remove_e}")
                    
                console.print(f"   ✅ Stopped and removed: {dev_name}")
                return True
            else:
                console.print(f"   ⚠️  No containers found for {dev_name}")
                return False
                
        except DockerError as e:
            console.print(f"   ❌ Error stopping {dev_name}: {e}")
            return False
    
    def list_containers(self) -> List[ContainerInfo]:
        """List all containers for the current project.
        
        Returns:
            List of ContainerInfo objects
        """
        try:
            project_labels = {
                "devs.project": self.project.info.name
            }
            
            containers = self.docker.find_containers_by_labels(project_labels)
            
            result = []
            for container_data in containers:
                dev_name = container_data['labels'].get('devs.dev', 'unknown')
                
                container_info = ContainerInfo(
                    name=container_data['name'],
                    dev_name=dev_name,
                    project_name=self.project.info.name,
                    status=container_data['status'],
                    container_id=container_data['id'],
                    created=_parse_docker_timestamp(container_data['created']),
                    labels=container_data['labels']
                )
                
                result.append(container_info)
            
            return result
            
        except DockerError as e:
            raise ContainerError(f"Failed to list containers: {e}")
    
    def find_aborted_containers(self, all_projects: bool = False) -> List[ContainerInfo]:
        """Find aborted devs containers that failed during setup.
        
        Args:
            all_projects: If True, find aborted containers for all projects
            
        Returns:
            List of ContainerInfo objects for aborted containers
        """
        try:
            # Look for containers with devs labels that are in failed states
            base_labels = {"devs.managed": "true"}
            if not all_projects:
                base_labels["devs.project"] = self.project.info.name
            
            containers = self.docker.find_containers_by_labels(base_labels)
            
            aborted_containers = []
            for container_data in containers:
                dev_name = container_data['labels'].get('devs.dev', 'unknown')
                project_name = container_data['labels'].get('devs.project', 'unknown')
                status = container_data['status'].lower()
                container_name = container_data['name']
                
                # Consider containers aborted if they are:
                # 1. In failed states: exited, dead, created but never started
                # 2. Running but with wrong name (indicates setup failure)
                is_failed_status = status in ['exited', 'dead', 'created']
                
                # Check if container has expected name for its dev environment
                expected_container_info = self._get_container_info(dev_name)
                expected_name = expected_container_info["container_name"]
                has_wrong_name = container_name != expected_name and dev_name != 'unknown'
                
                if is_failed_status or has_wrong_name:
                    container_info = ContainerInfo(
                        name=container_name,
                        dev_name=dev_name,
                        project_name=project_name,
                        status=container_data['status'],
                        container_id=container_data['id'],
                        created=_parse_docker_timestamp(container_data['created']),
                        labels=container_data['labels']
                    )
                    
                    aborted_containers.append(container_info)
            
            return aborted_containers
            
        except DockerError as e:
            raise ContainerError(f"Failed to find aborted containers: {e}")
    
    def remove_aborted_containers(self, containers: List[ContainerInfo]) -> int:
        """Remove a list of aborted containers.
        
        Args:
            containers: List of ContainerInfo objects to remove
            
        Returns:
            Number of containers successfully removed
        """
        removed_count = 0
        
        for container in containers:
            try:
                console.print(f"   🗑️  Removing aborted container: {container.name} ({container.status})")
                
                # Stop container first if it's running
                if container.status.lower() in ['running', 'restarting']:
                    console.print(f"   🛑 Stopping running container: {container.name}")
                    self.docker.stop_container(container.name)
                
                # Remove the container
                self.docker.remove_container(container.name)
                removed_count += 1
                
            except DockerError as e:
                console.print(f"   ❌ Failed to remove {container.name}: {e}")
                continue
        
        return removed_count
    
    def _prepare_container_exec(self, dev_name: str, workspace_dir: Path, debug: bool = False, live: bool = False, extra_env: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        """Prepare container for exec operations (shared by exec_shell and exec_command).
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            debug: Show debug output for devcontainer operations
            live: Whether the container is in live mode
            extra_env: Additional environment variables to pass to container
            
        Returns:
            Tuple of (container_name, container_workspace_dir)
            
        Raises:
            ContainerError: If container preparation fails
        """
        # Get initial container info (may be updated based on existing container mode)
        workspace_info = self._get_container_info(dev_name, live)
        container_name = workspace_info["container_name"]
        
        # Check if container already exists and detect its mode
        project_labels = self._get_project_labels(dev_name)
        existing_containers = self.docker.find_containers_by_labels(project_labels)
        if existing_containers:
            existing_container = existing_containers[0]
            existing_labels = existing_container.get('labels', {})
            existing_is_live = existing_labels.get('devs.live') == 'true'
            # Use the existing container's mode
            live = existing_is_live
        
        # In live mode, use the host folder name; otherwise use constructed name
        if live:
            workspace_name = workspace_dir.name
        else:
            workspace_name = workspace_info["workspace_name"]
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        # Ensure container is running
        if not self.ensure_container_running(dev_name, workspace_dir, debug=debug, live=live, extra_env=extra_env):
            raise ContainerError(f"Failed to start container for {dev_name}")
        
        return container_name, container_workspace_dir
    
    def exec_shell(self, dev_name: str, workspace_dir: Path, debug: bool = False, live: bool = False) -> None:
        """Execute a shell in the container.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            debug: Show debug output for devcontainer operations
            live: Whether the container is in live mode
            
        Raises:
            ContainerError: If shell execution fails
        """
        try:
            # Prepare container for execution
            container_name, container_workspace_dir = self._prepare_container_exec(
                dev_name, workspace_dir, debug=debug, live=live
            )
            
            console.print(f"🐚 Opening shell in: {dev_name} (container: {container_name})")
            console.print(f"   Workspace: {container_workspace_dir}")
            
            # Use docker exec to get an interactive shell
            # Start in the specific workspace directory using shell command
            shell_cmd = f"cd {container_workspace_dir} && exec /bin/zsh"
            cmd = [
                'docker', 'exec', '-it',
                container_name, 
                '/bin/bash', '-c', shell_cmd
            ]
            
            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
            
            subprocess.run(cmd, check=True)
            
        except (DockerError, subprocess.SubprocessError) as e:
            raise ContainerError(f"Failed to exec shell in {dev_name}: {e}")
    
    def exec_command(self, dev_name: str, workspace_dir: Path, command: str, stdin_input: Optional[str] = None, debug: bool = False, stream: bool = True, live: bool = False, extra_env: Optional[Dict[str, str]] = None) -> tuple[bool, str, str, int]:
        """Execute a command in the container.

        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            command: Command to execute
            stdin_input: Optional input to send via stdin
            debug: Show debug output for devcontainer operations
            stream: Stream output to console in real-time
            live: Whether the container is in live mode
            extra_env: Additional environment variables to pass to container

        Returns:
            Tuple of (success, stdout, stderr, exit_code)

        Raises:
            ContainerError: If command execution fails
        """
        try:
            # Prepare container for execution
            container_name, container_workspace_dir = self._prepare_container_exec(
                dev_name, workspace_dir, debug=debug, live=live, extra_env=extra_env
            )
            
            # Only print status messages if not in webhook mode (or if streaming)
            if os.environ.get('DEVS_WEBHOOK_MODE') != '1' or stream:
                console.print(f"🔧 Running command in: {dev_name} (container: {container_name})")
                console.print(f"   Workspace: {container_workspace_dir}")
                console.print(f"   Command: {command}")
            
            # Execute command in the container
            # Use same pattern as exec_shell: cd to workspace directory then run command
            # Explicitly source .zshrc to ensure environment is set up properly
            # Redirect source output to stderr to avoid corrupting stdout (important for webhook JSON output)
            full_cmd = f"source ~/.zshrc >/dev/stderr 2>&1 && cd {container_workspace_dir} && {command}"
            cmd = [
                'docker', 'exec', '-i',  # -i for stdin, no TTY
                container_name,
                '/bin/zsh', '-c', full_cmd  # Use zsh with explicit sourcing
            ]
            
            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
            
            if stream:
                # Stream output in real-time
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1  # Line buffered
                )
                
                # Send stdin input if provided and close stdin
                if process.stdin and stdin_input:
                    # Ensure stdin input ends with newline for proper command termination
                    if not stdin_input.endswith('\n'):
                        stdin_input = stdin_input + '\n'
                    process.stdin.write(stdin_input)
                    process.stdin.close()
                elif process.stdin:
                    process.stdin.close()
                
                # Collect output while streaming
                stdout_lines = []
                stderr_lines = []
                
                # Stream stdout
                if process.stdout:
                    for line in iter(process.stdout.readline, ''):
                        line = line.rstrip()
                        if line:
                            console.print(line)  # Stream to console
                            stdout_lines.append(line)
                    process.stdout.close()
                
                # Wait for process to complete
                process.wait()
                
                # Collect any stderr
                if process.stderr:
                    stderr_content = process.stderr.read()
                    if stderr_content:
                        console.print(f"[red]Error: {stderr_content}[/red]")
                        stderr_lines.append(stderr_content)
                    process.stderr.close()
                
                stdout = '\n'.join(stdout_lines)
                stderr = '\n'.join(stderr_lines)
                success = process.returncode == 0
                exit_code = process.returncode

            else:
                # Non-streaming mode (original behavior)
                process = subprocess.run(
                    cmd,
                    input=stdin_input if stdin_input else None,  # text=True means subprocess handles encoding
                    capture_output=True,
                    text=True
                )
                
                stdout = process.stdout if process.stdout else ""
                stderr = process.stderr if process.stderr else ""
                success = process.returncode == 0
                exit_code = process.returncode

            if debug:
                console.print(f"[dim]Command exit code: {process.returncode}[/dim]")
                if not stream:  # Only show this in debug if not already streamed
                    if stdout:
                        console.print(f"[dim]Command stdout: {stdout[:200]}...[/dim]")
                    if stderr:
                        console.print(f"[dim]Command stderr: {stderr[:200]}...[/dim]")
            
            if not success and stdout:
                # If stderr is empty but stdout contains error patterns, use stdout as error
                if not stderr:
                    stderr = stdout

            return success, stdout, stderr, exit_code

        except (DockerError, subprocess.SubprocessError) as e:
            raise ContainerError(f"Failed to exec command in {dev_name}: {e}")
    
    def exec_claude(self, dev_name: str, workspace_dir: Path, prompt: str, debug: bool = False, stream: bool = True, live: bool = False, extra_env: Optional[Dict[str, str]] = None) -> tuple[bool, str, str, int]:
        """Execute Claude CLI in the container.

        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            prompt: Prompt to send to Claude
            debug: Show debug output for devcontainer operations
            stream: Stream output to console in real-time
            live: Whether the container is in live mode
            extra_env: Additional environment variables to pass to container

        Returns:
            Tuple of (success, stdout, stderr, exit_code)

        Raises:
            ContainerError: If Claude execution fails
        """
        # Simply delegate to exec_command with the Claude command and prompt as stdin
        return self.exec_command(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            command="claude --dangerously-skip-permissions",
            stdin_input=prompt,
            debug=debug,
            stream=stream,
            live=live,
            extra_env=extra_env
        )

    def exec_codex(self, dev_name: str, workspace_dir: Path, prompt: str, debug: bool = False, stream: bool = True, live: bool = False, extra_env: Optional[Dict[str, str]] = None) -> tuple[bool, str, str, int]:
        """Execute OpenAI Codex CLI in the container.

        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            prompt: Prompt to send to Codex
            debug: Show debug output for devcontainer operations
            stream: Stream output to console in real-time
            live: Whether the container is in live mode
            extra_env: Additional environment variables to pass to container

        Returns:
            Tuple of (success, stdout, stderr, exit_code)

        Raises:
            ContainerError: If Codex execution fails
        """
        # Simply delegate to exec_command with the Codex command and prompt as stdin
        return self.exec_command(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            command="codex --full-auto",
            stdin_input=prompt,
            debug=debug,
            stream=stream,
            live=live,
            extra_env=extra_env
        )