"""Container management and lifecycle operations."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess
import aiodocker
import asyncio
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
        """Ensure a container is running (sync wrapper around async version).
        
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
        try:
            return asyncio.run(self.ensure_container_running_async(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                force_rebuild=force_rebuild,
                debug=debug
            ))
        except Exception as e:
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
        """Execute Claude CLI in the container (sync wrapper around async version).
        
        This is a sync wrapper that internally uses the async implementation
        to avoid file descriptor inheritance issues while maintaining the
        sync interface for CLI compatibility.
        
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
        import asyncio
        
        # Run the async version in a new event loop
        try:
            success, stdout, stderr = asyncio.run(self.exec_claude_async(
                dev_name=dev_name,
                workspace_dir=workspace_dir, 
                prompt=prompt,
                debug=debug
            ))
            
            # Show output in CLI mode (when stream=True)
            if stream and stdout:
                console.print(stdout)
            
            if stderr:
                console.print(f"[red]Error: {stderr}[/red]")
            
            return success, stdout, stderr
            
        except Exception as e:
            raise ContainerError(f"Failed to exec Claude in {dev_name}: {e}")
    
    async def exec_claude_async(self, dev_name: str, workspace_dir: Path, prompt: str, debug: bool = False) -> tuple[bool, str, str]:
        """Execute Claude CLI in the container asynchronously.
        
        This is an async version that avoids file descriptor inheritance issues
        that can occur when running in thread pools.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            prompt: Prompt to send to Claude
            debug: Show debug output for devcontainer operations
            
        Returns:
            Tuple of (success, stdout, stderr)
            
        Raises:
            ContainerError: If Claude execution fails
        """
        import asyncio
        
        # Handle workspace creation/reset if needed
        if workspace_dir is None:
            from .workspace import WorkspaceManager
            workspace_manager = WorkspaceManager(self.project, self.config)
            workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=False)
        
        project_prefix = self.config.project_prefix if self.config else "dev"
        container_name = self.project.get_container_name(dev_name, project_prefix)
        workspace_name = self.project.get_workspace_name(dev_name)
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        try:
            # Ensure container is running (async)
            if not await self.ensure_container_running_async(dev_name, workspace_dir, debug=debug):
                raise ContainerError(f"Failed to start container for {dev_name}")
            
            console.print(f"🤖 Running Claude in: {dev_name} (container: {container_name})")
            console.print(f"   Workspace: {container_workspace_dir}")
            
            # Execute Claude CLI in the container using async subprocess
            claude_cmd = f"source ~/.zshrc && cd {container_workspace_dir} && claude --dangerously-skip-permissions"
            cmd = [
                'docker', 'exec', '-i',  # -i for stdin, no TTY
                container_name,
                '/bin/zsh', '-c', claude_cmd  # Use zsh with explicit sourcing
            ]
            
            if debug:
                console.print(f"[dim]Running async: {' '.join(cmd)}[/dim]")
            
            # Use async subprocess to avoid file descriptor inheritance issues
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send prompt and get results
            stdout_data, stderr_data = await process.communicate(prompt.encode('utf-8'))
            
            stdout = stdout_data.decode('utf-8', errors='replace') if stdout_data else ""
            stderr = stderr_data.decode('utf-8', errors='replace') if stderr_data else ""
            success = process.returncode == 0
            
            if debug:
                console.print(f"[dim]Claude async exit code: {process.returncode}[/dim]")
                if stdout:
                    console.print(f"[dim]Claude async stdout: {stdout[:200]}...[/dim]")
                if stderr:
                    console.print(f"[dim]Claude async stderr: {stderr[:200]}...[/dim]")
            
            return success, stdout, stderr
            
        except (DockerError, Exception) as e:
            raise ContainerError(f"Failed to exec Claude async in {dev_name}: {e}")
    
    async def ensure_container_running_async(
        self, 
        dev_name: str,
        workspace_dir: Path,
        force_rebuild: bool = False,
        debug: bool = False
    ) -> bool:
        """Ensure a container is running for the specified dev environment (async version).
        
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
            console.print(f"[yellow]🔍 Starting async container setup for {dev_name}[/yellow]")
            # Use aiodocker for async Docker operations
            docker = aiodocker.Docker()
            console.print(f"   🐳 Connected to Docker daemon via aiodocker")
            
            try:
                # Check if we need to rebuild (still sync for now)
                rebuild_needed, rebuild_reason = self.should_rebuild_image(dev_name)
                if rebuild_needed or force_rebuild:
                    if force_rebuild:
                        console.print(f"   🔄 Forcing image rebuild for {dev_name}...")
                    else:
                        console.print(f"   🔄 {rebuild_reason}, rebuilding image...")
                    
                    # Stop existing container if running (async)
                    containers = await self._find_containers_by_labels_async(docker, project_labels)
                    for container_info in containers:
                        if debug:
                            console.print(f"[dim]Stopping container: {container_info['name']}[/dim]")
                        await self._stop_container_async(docker, container_info['name'])
                        if debug:
                            console.print(f"[dim]Removing container: {container_info['name']}[/dim]")
                        await self._remove_container_async(docker, container_info['name'])
                
                # Check if container is already running (async)
                if debug:
                    console.print(f"[dim]Checking for existing containers with labels: {project_labels}[/dim]")
                existing_containers = await self._find_containers_by_labels_async(docker, project_labels)
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
                        await self._remove_container_async(docker, container_info['name'], force=True)
                
                console.print(f"   🚀 Starting container for {dev_name}...")
                
                # Use async devcontainer up
                success = await self._devcontainer_up_async(
                    workspace_dir=workspace_dir,
                    dev_name=dev_name,
                    rebuild=rebuild_needed or force_rebuild,
                    debug=debug
                )
                
                if not success:
                    raise ContainerError(f"Failed to start devcontainer for {dev_name}")
                
                # Get the created container and verify it's healthy (async)
                if debug:
                    console.print(f"[dim]Looking for created containers with labels: {project_labels}[/dim]")
                created_containers = await self._find_containers_by_labels_async(docker, project_labels)
                if not created_containers:
                    raise ContainerError(f"No container found after devcontainer up for {dev_name}")
                
                created_container = created_containers[0]
                container_name_actual = created_container['name']
                
                if debug:
                    console.print(f"[dim]Found created container: {container_name_actual}[/dim]")
                
                # Test container health (async)
                console.print(f"   🔍 Checking container health for {dev_name}...")
                if debug:
                    console.print(f"[dim]Running health check: docker exec {container_name_actual} echo 'Container ready'[/dim]")
                if not await self._exec_command_async(docker, container_name_actual, "echo 'Container ready'"):
                    raise ContainerError(f"Container {dev_name} is not responding")
                
                console.print(f"   ✅ Started: {dev_name}")
                return True
            
            finally:
                await docker.close()
                
        except Exception as e:
            # Clean up any failed containers (async)
            try:
                docker = aiodocker.Docker()
                try:
                    failed_containers = await self._find_containers_by_labels_async(docker, project_labels)
                    for container_info in failed_containers:
                        await self._stop_container_async(docker, container_info['name'])
                        await self._remove_container_async(docker, container_info['name'])
                finally:
                    await docker.close()
            except Exception:
                pass
            
            raise ContainerError(f"Failed to ensure container running for {dev_name}: {e}")
    
    async def _find_containers_by_labels_async(self, docker, labels: dict) -> list:
        """Find containers by labels using aiodocker."""
        try:
            containers = await docker.containers.list()
            matching_containers = []
            
            for container in containers:
                container_labels = container._container.get('Labels', {})
                if container_labels and all(container_labels.get(k) == v for k, v in labels.items()):
                    matching_containers.append({
                        'name': container._container['Names'][0].lstrip('/'),
                        'status': container._container['State'].lower(),
                        'id': container._container['Id'],
                        'labels': container_labels
                    })
            
            return matching_containers
        except Exception as e:
            console.print(f"[red]Error finding containers by labels: {e}[/red]")
            return []
    
    async def _stop_container_async(self, docker, container_name: str) -> bool:
        """Stop a container using aiodocker."""
        try:
            container = await docker.containers.get(container_name)
            await container.stop()
            return True
        except Exception as e:
            console.print(f"[yellow]Warning: Could not stop container {container_name}: {e}[/yellow]")
            return False
    
    async def _remove_container_async(self, docker, container_name: str, force: bool = False) -> bool:
        """Remove a container using aiodocker."""
        try:
            container = await docker.containers.get(container_name)
            await container.delete(force=force)
            return True
        except Exception as e:
            console.print(f"[yellow]Warning: Could not remove container {container_name}: {e}[/yellow]")
            return False
    
    async def _exec_command_async(self, docker, container_name: str, command: str) -> bool:
        """Execute a command in a container using aiodocker."""
        try:
            container = await docker.containers.get(container_name)
            result = await container.exec(['/bin/sh', '-c', command])
            return result.get('ExitCode', 1) == 0
        except Exception as e:
            console.print(f"[yellow]Warning: Could not exec command in {container_name}: {e}[/yellow]")
            return False
    
    async def _devcontainer_up_async(self, workspace_dir: Path, dev_name: str, rebuild: bool, debug: bool) -> bool:
        """Run devcontainer up using async subprocess."""
        import asyncio
        from ..utils.devcontainer import DevContainerCLI
        
        try:
            # For now, use the existing DevContainerCLI but in an async subprocess
            devcontainer_cli = DevContainerCLI(self.config)
            
            # Run the devcontainer up in an async subprocess to avoid blocking
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,  # Use default thread pool executor
                lambda: devcontainer_cli.up(
                    workspace_folder=workspace_dir,
                    dev_name=dev_name,
                    project_name=self.project.info.name,
                    git_remote_url=self.project.info.git_remote_url,
                    rebuild=rebuild,
                    remove_existing=True,
                    debug=debug,
                    config_path=None  # Use workspace devcontainer if available
                )
            )
            
            return success
            
        except Exception as e:
            console.print(f"[red]Async devcontainer up failed: {e}[/red]")
            return False
    
