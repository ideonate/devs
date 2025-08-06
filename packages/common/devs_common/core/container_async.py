"""Async container management and lifecycle operations."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import BaseConfig
from ..exceptions import ContainerError, DockerError
from ..utils.docker_client_async import AsyncDockerClient
from ..utils.devcontainer_async import AsyncDevContainerCLI
from ..utils.devcontainer_template import get_template_dir
from .project import Project


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


class AsyncContainerManager:
    """Async manager for Docker containers for devcontainer environments."""
    
    def __init__(self, project: Project, config: Optional[BaseConfig] = None) -> None:
        """Initialize async container manager.
        
        Args:
            project: Project instance
            config: Configuration instance (optional)
        """
        self.project = project
        self.config = config
        self.devcontainer = AsyncDevContainerCLI(config)
    
    async def should_rebuild_image(self, dev_name: str) -> Tuple[bool, str]:
        """Check if devcontainer image should be rebuilt.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Tuple of (should_rebuild, reason)
        """
        async with AsyncDockerClient() as docker:
            try:
                # Find existing images for this devcontainer configuration
                image_pattern = f"vsc-{self.project.info.name}-{dev_name}-"
                existing_images = await docker.find_images_by_pattern(image_pattern)
                
                if not existing_images:
                    return False, "No existing image found"
                
                # Get the newest image creation time
                newest_image_time = None
                for image_name in existing_images:
                    image_time = await docker.get_image_creation_time(image_name)
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
                            for sub_path in file_path.rglob('*'):
                                if sub_path.is_file():
                                    file_time = datetime.fromtimestamp(sub_path.stat().st_mtime)
                                    if file_time > newest_image_time:
                                        return True, f"File newer than image: {sub_path.relative_to(self.project.project_dir)}"
                
                return False, "No rebuild needed"
                
            except DockerError:
                # If Docker operations fail, don't rebuild
                return False, "Could not check image status"
    
    async def ensure_container_running(
        self, 
        dev_name: str, 
        workspace_dir: Path,
        rebuild: bool = False,
        debug: bool = False
    ) -> bool:
        """Ensure container is running for the dev environment.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory path
            rebuild: Force rebuild of the container
            debug: Enable debug output
            
        Returns:
            True if container is running
            
        Raises:
            ContainerError: If container operations fail
        """
        container_name = self.project.get_container_name(dev_name)
        
        # Check if we should rebuild based on file changes
        if not rebuild:
            should_rebuild, reason = await self.should_rebuild_image(dev_name)
            if should_rebuild:
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]⚠️  Rebuilding image: {reason}[/yellow]")
                rebuild = True
        
        # Check if devcontainer template should be used
        config_path = None
        if not (self.project.project_dir / ".devcontainer").exists():
            template_dir = get_template_dir()
            if template_dir and template_dir.exists():
                config_path = template_dir
                from rich.console import Console
                console = Console()
                console.print(f"[dim]Using devcontainer template from {template_dir}[/dim]")
        
        # Use devcontainer CLI to start container
        try:
            success = await self.devcontainer.up(
                workspace_folder=workspace_dir,
                dev_name=dev_name,
                project_name=self.project.info.name,
                git_remote_url=self.project.info.git_url,
                rebuild=rebuild,
                remove_existing=rebuild,
                debug=debug,
                config_path=config_path
            )
            
            if not success:
                raise ContainerError(f"Failed to start container {container_name}")
                
            return True
            
        except Exception as e:
            raise ContainerError(f"Container startup failed: {e}")
    
    async def stop_container(self, dev_name: str) -> bool:
        """Stop and remove a container.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            True if container was stopped
        """
        async with AsyncDockerClient() as docker:
            try:
                # Find containers by labels for more reliable matching
                labels = {
                    'devs.project': self.project.info.name,
                    'devs.dev': dev_name
                }
                
                containers = await docker.find_containers_by_labels(labels)
                
                if not containers:
                    return False
                
                # Stop and remove all matching containers
                for container in containers:
                    container_name = container['name']
                    
                    # Stop container
                    await docker.stop_container(container_name)
                    
                    # Remove container
                    await docker.remove_container(container_name, force=True)
                
                return True
                
            except DockerError:
                return False
    
    async def list_containers(self) -> List[ContainerInfo]:
        """List all containers for the current project.
        
        Returns:
            List of container information
        """
        async with AsyncDockerClient() as docker:
            try:
                # Find containers by project label
                labels = {'devs.project': self.project.info.name}
                containers = await docker.find_containers_by_labels(labels)
                
                result = []
                for container in containers:
                    # Extract dev name from labels
                    dev_name = container['labels'].get('devs.dev', 'unknown')
                    
                    # Parse creation time
                    created = None
                    if container.get('created'):
                        try:
                            created = datetime.fromisoformat(
                                container['created'].replace('Z', '+00:00')
                            )
                        except ValueError:
                            pass
                    
                    result.append(ContainerInfo(
                        name=container['name'],
                        dev_name=dev_name,
                        project_name=self.project.info.name,
                        status=container['status'],
                        container_id=container['id'],
                        created=created,
                        labels=container['labels']
                    ))
                
                return result
                
            except DockerError:
                return []
    
    async def find_aborted_containers(self, all_projects: bool = False) -> List[ContainerInfo]:
        """Find aborted devs containers that failed during setup.
        
        Args:
            all_projects: If True, find aborted containers across all projects
            
        Returns:
            List of aborted container information
        """
        async with AsyncDockerClient() as docker:
            try:
                # Find containers with aborted label
                labels = {'devs.status': 'aborted'}
                if not all_projects:
                    labels['devs.project'] = self.project.info.name
                
                containers = await docker.find_containers_by_labels(labels)
                
                result = []
                for container in containers:
                    dev_name = container['labels'].get('devs.dev', 'unknown')
                    project_name = container['labels'].get('devs.project', 'unknown')
                    
                    created = None
                    if container.get('created'):
                        try:
                            created = datetime.fromisoformat(
                                container['created'].replace('Z', '+00:00')
                            )
                        except ValueError:
                            pass
                    
                    result.append(ContainerInfo(
                        name=container['name'],
                        dev_name=dev_name,
                        project_name=project_name,
                        status='aborted',
                        container_id=container['id'],
                        created=created,
                        labels=container['labels']
                    ))
                
                return result
                
            except DockerError:
                return []
    
    async def remove_aborted_containers(self, containers: List[ContainerInfo]) -> int:
        """Remove a list of aborted containers.
        
        Args:
            containers: List of containers to remove
            
        Returns:
            Number of containers removed
        """
        removed_count = 0
        
        async with AsyncDockerClient() as docker:
            for container in containers:
                try:
                    await docker.remove_container(container.name, force=True)
                    removed_count += 1
                except DockerError:
                    pass
        
        return removed_count
    
    async def exec_shell(self, dev_name: str, workspace_dir: Path, debug: bool = False) -> None:
        """Execute an interactive shell in the container.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory
            debug: Enable debug output
        """
        # For interactive shell, we need to use subprocess directly
        # This cannot be fully async as it needs TTY interaction
        import subprocess
        import sys
        
        container_name = self.project.get_container_name(dev_name)
        
        # Ensure container is running
        await self.ensure_container_running(dev_name, workspace_dir, debug=debug)
        
        # Use docker exec with TTY
        cmd = [
            "docker", "exec", "-it", container_name,
            "/bin/bash", "-l"
        ]
        
        # Run in foreground with TTY
        subprocess.run(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
    
    async def exec_claude_async(
        self, 
        dev_name: str, 
        workspace_dir: Path, 
        prompt: str, 
        debug: bool = False
    ) -> tuple[bool, str, str]:
        """Execute Claude CLI in the container asynchronously.
        
        Args:
            dev_name: Development environment name
            workspace_dir: Workspace directory
            prompt: Claude prompt to execute
            debug: Enable debug output
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        container_name = self.project.get_container_name(dev_name)
        
        # Ensure container is running
        await self.ensure_container_running(dev_name, workspace_dir, debug=debug)
        
        # Execute Claude command
        command = [
            "/bin/zsh", "-l", "-c",
            f"cd /home/node && claude '{prompt}'"
        ]
        
        success, stdout, stderr = await self.devcontainer.exec_command(
            workspace_folder=workspace_dir,
            command=command,
            timeout=600.0  # 10 minutes for Claude operations
        )
        
        return success, stdout, stderr