"""Container management and lifecycle operations."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import config
from ..exceptions import ContainerError, DockerError
from ..utils.docker_client import DockerClient
from ..utils.devcontainer import DevContainerCLI
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
    
    def __init__(self, project: Project) -> None:
        """Initialize container manager.
        
        Args:
            project: Project instance
        """
        self.project = project
        self.docker = DockerClient()
        self.devcontainer = DevContainerCLI()
    
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
        force_rebuild: bool = False
    ) -> bool:
        """Ensure a container is running for the specified dev environment.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            force_rebuild: Force rebuild even if not needed
            
        Returns:
            True if container is running successfully
            
        Raises:
            ContainerError: If container operations fail
        """
        container_name = self.project.get_container_name(dev_name, config.project_prefix)
        project_labels = {
            "devs.project": self.project.info.name,
            "devs.dev": dev_name,
            **config.container_labels
        }
        
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
                    self.docker.stop_container(container_info['name'])
                    self.docker.remove_container(container_info['name'])
            
            # Check if container is already running
            existing_containers = self.docker.find_containers_by_labels(project_labels)
            if existing_containers and not (rebuild_needed or force_rebuild):
                container_info = existing_containers[0]
                if container_info['status'] == 'running':
                    return True
                else:
                    # Container exists but not running, remove it
                    self.docker.remove_container(container_info['name'], force=True)
            
            console.print(f"   🚀 Starting container for {dev_name}...")
            
            # Start devcontainer
            success = self.devcontainer.up(
                workspace_folder=workspace_dir,
                dev_name=dev_name,
                project_name=self.project.info.name,
                git_remote_url=self.project.info.git_remote_url,
                rebuild=rebuild_needed or force_rebuild,
                remove_existing=True
            )
            
            if not success:
                raise ContainerError(f"Failed to start devcontainer for {dev_name}")
            
            # Get the created container and verify it's healthy
            created_containers = self.docker.find_containers_by_labels(project_labels)
            if not created_containers:
                raise ContainerError(f"No container found after devcontainer up for {dev_name}")
            
            created_container = created_containers[0]
            container_name_actual = created_container['name']
            
            # Test container health
            console.print(f"   🔍 Checking container health for {dev_name}...")
            if not self.docker.exec_command(container_name_actual, "echo 'Container ready'"):
                raise ContainerError(f"Container {dev_name} is not responding")
            
            # Rename container if needed
            if container_name_actual != container_name:
                try:
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
        """Stop and remove a container.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            True if container was stopped/removed
        """
        container_name = self.project.get_container_name(dev_name, config.project_prefix)
        
        try:
            if self.docker.container_exists(container_name):
                self.docker.stop_container(container_name)
                self.docker.remove_container(container_name)
                console.print(f"   ✅ Stopped and removed: {dev_name}")
                return True
            else:
                console.print(f"   ⚠️  Container not found: {dev_name}")
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
    
    def exec_shell(self, dev_name: str, workspace_dir: Path) -> None:
        """Execute a shell in the container.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            
        Raises:
            ContainerError: If shell execution fails
        """
        container_name = self.project.get_container_name(dev_name, config.project_prefix)
        workspace_name = self.project.get_workspace_name(dev_name)
        container_workspace_dir = f"/workspaces/{workspace_name}"
        
        try:
            # Ensure container is running
            if not self.ensure_container_running(dev_name, workspace_dir):
                raise ContainerError(f"Failed to start container for {dev_name}")
            
            console.print(f"🐚 Opening shell in: {dev_name} (container: {container_name})")
            console.print(f"   Workspace: {container_workspace_dir}")
            
            # Use docker exec to get an interactive shell
            import subprocess
            
            cmd = [
                'docker', 'exec', '-it', 
                '-w', container_workspace_dir,
                container_name, '/bin/zsh'
            ]
            
            subprocess.run(cmd, check=True)
            
        except (DockerError, subprocess.SubprocessError) as e:
            raise ContainerError(f"Failed to exec shell in {dev_name}: {e}")