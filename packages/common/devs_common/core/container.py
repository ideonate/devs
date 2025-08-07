"""Container management and lifecycle operations."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess

from rich.console import Console

from ..config import BaseConfig
from ..exceptions import ContainerError, DockerError
from ..utils.docker_client import DockerClient
from ..utils.devcontainer import DevContainerCLI
from ..utils.devcontainer_template import get_template_dir
from .project import Project

console = Console()


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
    
    def should_rebuild_image(self, dev_name: str) -> Tuple[bool, str]:
        """Check if devcontainer image should be rebuilt.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Tuple of (should_rebuild, reason)
        """
        try:
            # Find existing images for this devcontainer configuration
            image_pattern = f"vsc-{self.project.info.name}-{dev_name}-"
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
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_time > newest_image_time:
                            return True, f"File newer than image: {file_path.name}"
                    elif file_path.is_dir():
                        # For directories, find the newest file
                        newest_file_time = None
                        newest_file = None
                        
                        for item in file_path.rglob('*'):
                            if item.is_file():
                                item_time = datetime.fromtimestamp(item.stat().st_mtime)
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
        debug: bool = False
    ) -> bool:
        """Ensure a container is running for the specified dev environment.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            force_rebuild: Force rebuild even if not needed
            debug: Show debug output for devcontainer operations
            
        Returns:
            True if container is running successfully
            
        Raises:
            ContainerError: If container operations fail
        """
        project_prefix = self.config.project_prefix if self.config else "dev"
        container_name = self.project.get_container_name(dev_name, project_prefix)
        project_labels = {
            "devs.project": self.project.info.name,
            "devs.dev": dev_name,
        }
        
        if self.config:
            project_labels.update(self.config.container_labels)
        
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
                for container_info in existing_containers:
                    if debug:
                        console.print(f"[dim]Stopping container: {container_info['name']}[/dim]")
                    self.docker.stop_container(container_info['name'])
                    if debug:
                        console.print(f"[dim]Removing container: {container_info['name']}[/dim]")
                    self.docker.remove_container(container_info['name'])
            
            # Check if container is already running
            if debug:
                console.print(f"[dim]Checking for existing containers with labels: {project_labels}[/dim]")
            existing_containers = self.docker.find_containers_by_labels(project_labels)
            if existing_containers and not (rebuild_needed or force_rebuild):
                container_info = existing_containers[0]
                if debug:
                    console.print(f"[dim]Found existing container: {container_info['name']} (status: {container_info['status']})[/dim]")
                if container_info['status'] == 'running':
                    if debug:
                        console.print(f"[dim]Container already running, skipping startup[/dim]")
                    return True
                else:
                    # Container exists but not running, remove it
                    if debug:
                        console.print(f"[dim]Container exists but not running, removing: {container_info['name']}[/dim]")
                    self.docker.remove_container(container_info['name'], force=True)
            
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
            success = self.devcontainer.up(
                workspace_folder=workspace_dir,
                dev_name=dev_name,
                project_name=self.project.info.name,
                git_remote_url=self.project.info.git_remote_url,
                rebuild=rebuild_needed or force_rebuild,
                remove_existing=True,
                debug=debug,
                config_path=config_path
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
        project_labels = {
            "devs.project": self.project.info.name,
            "devs.dev": dev_name,
        }
        
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
                    created=datetime.fromisoformat(container_data['created'].replace('Z', '+00:00')),
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
                expected_name = self.project.get_container_name(dev_name, self.config.project_prefix if self.config else "dev")
                has_wrong_name = container_name != expected_name and dev_name != 'unknown'
                
                if is_failed_status or has_wrong_name:
                    container_info = ContainerInfo(
                        name=container_name,
                        dev_name=dev_name,
                        project_name=project_name,
                        status=container_data['status'],
                        container_id=container_data['id'],
                        created=datetime.fromisoformat(container_data['created'].replace('Z', '+00:00')),
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
    
    def exec_shell(self, dev_name: str, workspace_dir: Path, debug: bool = False) -> None:
        """Execute a shell in the container.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            debug: Show debug output for devcontainer operations
            
        Raises:
            ContainerError: If shell execution fails
        """
        project_prefix = self.config.project_prefix if self.config else "dev"
        container_name = self.project.get_container_name(dev_name, project_prefix)
        workspace_name = self.project.get_workspace_name(dev_name)
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        try:
            # Ensure container is running
            if not self.ensure_container_running(dev_name, workspace_dir, debug=debug):
                raise ContainerError(f"Failed to start container for {dev_name}")
            
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
    
    def exec_claude(self, dev_name: str, workspace_dir: Path, prompt: str, debug: bool = False, stream: bool = True) -> tuple[bool, str, str]:
        """Execute Claude CLI in the container.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            prompt: Prompt to send to Claude
            debug: Show debug output for devcontainer operations
            stream: Stream output to console in real-time
            
        Returns:
            Tuple of (success, stdout, stderr)
            
        Raises:
            ContainerError: If Claude execution fails
        """
        project_prefix = self.config.project_prefix if self.config else "dev"
        container_name = self.project.get_container_name(dev_name, project_prefix)
        workspace_name = self.project.get_workspace_name(dev_name)
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        try:
            # Ensure container is running
            if not self.ensure_container_running(dev_name, workspace_dir, debug=debug):
                raise ContainerError(f"Failed to start container for {dev_name}")
            
            console.print(f"🤖 Running Claude in: {dev_name} (container: {container_name})")
            console.print(f"   Workspace: {container_workspace_dir}")
            
            # Execute Claude CLI in the container
            # Use same pattern as exec_shell: cd to workspace directory then run command
            # Explicitly source .zshrc to ensure CLAUDE_CONFIG_DIR is set in non-interactive mode
            claude_cmd = f"source ~/.zshrc && cd {container_workspace_dir} && claude --dangerously-skip-permissions"
            cmd = [
                'docker', 'exec', '-i',  # -i for stdin, no TTY
                container_name,
                '/bin/zsh', '-c', claude_cmd  # Use zsh with explicit sourcing
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
                
                # Send prompt and close stdin
                if process.stdin:
                    process.stdin.write(prompt)
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
                
            else:
                # Non-streaming mode (original behavior)
                process = subprocess.run(
                    cmd, 
                    input=prompt.encode('utf-8'),
                    capture_output=True
                )
                
                stdout = process.stdout.decode('utf-8', errors='replace') if process.stdout else ""
                stderr = process.stderr.decode('utf-8', errors='replace') if process.stderr else ""
                success = process.returncode == 0
            
            if debug:
                console.print(f"[dim]Claude exit code: {process.returncode}[/dim]")
                if not stream:  # Only show this in debug if not already streamed
                    if stdout:
                        console.print(f"[dim]Claude stdout: {stdout[:200]}...[/dim]")
                    if stderr:
                        console.print(f"[dim]Claude stderr: {stderr[:200]}...[/dim]")
            
            if not success and stdout:

                # If stderr is empty but stdout contains error patterns, use stdout as error
                if not stderr:
                    stderr = stdout
            
            return success, stdout, stderr
            
        except (DockerError, subprocess.SubprocessError) as e:
            raise ContainerError(f"Failed to exec Claude in {dev_name}: {e}")