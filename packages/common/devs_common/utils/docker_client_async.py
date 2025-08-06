"""Async Docker client utilities and wrapper."""

from datetime import datetime
import logging
from typing import Dict, List, Optional, Any

import aiodocker
from aiodocker.exceptions import DockerError as AioDockerError

from ..exceptions import DockerError


class AsyncDockerClient:
    """Async wrapper around Docker client with error handling."""
    
    def __init__(self) -> None:
        """Initialize Async Docker client."""
        self.client: Optional[aiodocker.Docker] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = aiodocker.Docker()
        try:
            # Test connection
            await self.client.ping()
        except AioDockerError as e:
            await self.client.close()
            raise DockerError(f"Failed to connect to Docker: {e}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.close()
    
    async def container_exists(self, name: str) -> bool:
        """Check if container exists.
        
        Args:
            name: Container name
            
        Returns:
            True if container exists
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(name)
            await container.show()
            return True
        except AioDockerError:
            return False
    
    async def container_is_running(self, name: str) -> bool:
        """Check if container is running.
        
        Args:
            name: Container name
            
        Returns:
            True if container is running
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(name)
            info = await container.show()
            return info['State']['Status'] == 'running'
        except AioDockerError:
            return False
    
    async def stop_container(self, name: str) -> None:
        """Stop a container.
        
        Args:
            name: Container name
            
        Raises:
            DockerError: If stopping fails
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(name)
            await container.stop()
        except AioDockerError as e:
            if "404" not in str(e):  # Not found is ok
                raise DockerError(f"Error stopping container {name}: {e}")
    
    async def remove_container(self, name: str, force: bool = False) -> None:
        """Remove a container.
        
        Args:
            name: Container name
            force: Force removal even if running
            
        Raises:
            DockerError: If removal fails
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(name)
            await container.delete(force=force)
        except AioDockerError as e:
            if "404" not in str(e):  # Not found is ok
                raise DockerError(f"Error removing container {name}: {e}")
    
    async def find_containers_by_labels(self, labels: Dict[str, str]) -> List[Dict[str, Any]]:
        """Find containers by labels.
        
        Args:
            labels: Dictionary of label key-value pairs to match
            
        Returns:
            List of container information dictionaries
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            # Build label filters
            filters = {"label": [f"{k}={v}" for k, v in labels.items()]}
            
            containers = await self.client.containers.list(all=True, filters=filters)
            
            logging.debug("Found containers by labels", labels=labels, count=len(containers))
            
            result = []
            for container in containers:
                info = await container.show()
                result.append({
                    'name': info['Name'].lstrip('/'),
                    'id': info['Id'],
                    'status': info['State']['Status'],
                    'labels': info['Config']['Labels'],
                    'created': info['Created'],
                })
            
            return result
            
        except AioDockerError as e:
            raise DockerError(f"Error finding containers by labels: {e}")
    
    async def rename_container(self, old_name: str, new_name: str) -> None:
        """Rename a container.
        
        Args:
            old_name: Current container name
            new_name: New container name
            
        Raises:
            DockerError: If rename fails
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(old_name)
            await container.rename(new_name)
        except AioDockerError as e:
            if "404" in str(e):
                raise DockerError(f"Container {old_name} not found")
            raise DockerError(f"Error renaming container {old_name} to {new_name}: {e}")
    
    async def exec_command(self, container_name: str, command: str, workdir: Optional[str] = None) -> bool:
        """Execute a command in a container.
        
        Args:
            container_name: Container name
            command: Command to execute
            workdir: Working directory for command
            
        Returns:
            True if command succeeded
            
        Raises:
            DockerError: If execution fails
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            container = await self.client.containers.get(container_name)
            
            # Create exec instance
            exec_config = {
                "Cmd": command.split() if isinstance(command, str) else command,
                "AttachStdout": True,
                "AttachStderr": True,
                "Tty": False,
            }
            if workdir:
                exec_config["WorkingDir"] = workdir
            
            exec_instance = await container.exec(exec_config)
            
            # Start and wait for completion
            stream = exec_instance.start(detach=False)
            output = b""
            async for chunk in stream:
                output += chunk
            
            # Get exit code
            exec_info = await exec_instance.inspect()
            return exec_info["ExitCode"] == 0
            
        except AioDockerError as e:
            if "404" in str(e):
                raise DockerError(f"Container {container_name} not found")
            raise DockerError(f"Error executing command in {container_name}: {e}")
    
    async def get_image_creation_time(self, image_name: str) -> Optional[datetime]:
        """Get image creation time.
        
        Args:
            image_name: Image name or ID
            
        Returns:
            Image creation datetime, or None if not found
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            image = await self.client.images.get(image_name)
            info = await image.inspect()
            created_str = info['Created']
            # Parse Docker's ISO format
            return datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        except AioDockerError:
            return None
        except ValueError as e:
            raise DockerError(f"Error parsing image creation time for {image_name}: {e}")
    
    async def find_images_by_pattern(self, pattern: str) -> List[str]:
        """Find images matching a name pattern.
        
        Args:
            pattern: Image name pattern to match
            
        Returns:
            List of matching image names
        """
        if not self.client:
            raise DockerError("Client not initialized. Use async context manager.")
        
        try:
            images = await self.client.images.list()
            matching = []
            
            for image in images:
                if 'RepoTags' in image and image['RepoTags']:
                    for tag in image['RepoTags']:
                        if pattern in tag:
                            matching.append(tag)
            
            return matching
            
        except AioDockerError as e:
            raise DockerError(f"Error finding images by pattern {pattern}: {e}")