"""Docker client utilities and wrapper."""

from datetime import datetime
import logging
import re
from typing import Dict, List, Optional, Any

import docker
from docker.errors import DockerException, NotFound, APIError

from ..exceptions import DockerError


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


class DockerClient:
    """Wrapper around Docker client with error handling."""
    
    def __init__(self) -> None:
        """Initialize Docker client."""
        try:
            self.client = docker.from_env()
            # Test connection
            self.client.ping()
        except DockerException as e:
            raise DockerError(f"Failed to connect to Docker: {e}")
    
    def container_exists(self, name: str) -> bool:
        """Check if container exists.
        
        Args:
            name: Container name
            
        Returns:
            True if container exists
        """
        try:
            self.client.containers.get(name)
            return True
        except NotFound:
            return False
        except DockerException as e:
            raise DockerError(f"Error checking container {name}: {e}")
    
    def container_is_running(self, name: str) -> bool:
        """Check if container is running.
        
        Args:
            name: Container name
            
        Returns:
            True if container is running
        """
        try:
            container = self.client.containers.get(name)
            return container.status == 'running'
        except NotFound:
            return False
        except DockerException as e:
            raise DockerError(f"Error checking container status {name}: {e}")
    
    def stop_container(self, name: str) -> None:
        """Stop a container.
        
        Args:
            name: Container name
            
        Raises:
            DockerError: If stopping fails
        """
        try:
            container = self.client.containers.get(name)
            container.stop()
        except NotFound:
            # Already stopped/doesn't exist
            pass
        except DockerException as e:
            raise DockerError(f"Error stopping container {name}: {e}")
    
    def remove_container(self, name: str, force: bool = False) -> None:
        """Remove a container.
        
        Args:
            name: Container name
            force: Force removal even if running
            
        Raises:
            DockerError: If removal fails
        """
        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
        except NotFound:
            # Already removed
            pass
        except DockerException as e:
            raise DockerError(f"Error removing container {name}: {e}")
    
    def find_containers_by_labels(self, labels: Dict[str, str]) -> List[Dict[str, Any]]:
        """Find containers by labels.
        
        Args:
            labels: Dictionary of label key-value pairs to match
            
        Returns:
            List of container information dictionaries
        """
        try:
            # Build label filters
            label_filters = []
            for key, value in labels.items():
                label_filters.append(f"{key}={value}")
            
            containers = self.client.containers.list(
                all=True, 
                filters={'label': label_filters}
            )

            logging.debug("Found containers by labels", labels=labels, count=len(containers))
            
            result = []
            for container in containers:
                result.append({
                    'name': container.name,
                    'id': container.id,
                    'status': container.status,
                    'labels': container.labels,
                    'created': container.attrs['Created'],
                })
            
            return result
            
        except DockerException as e:
            raise DockerError(f"Error finding containers by labels: {e}")
    
    def rename_container(self, old_name: str, new_name: str) -> None:
        """Rename a container.
        
        Args:
            old_name: Current container name
            new_name: New container name
            
        Raises:
            DockerError: If rename fails
        """
        try:
            container = self.client.containers.get(old_name)
            container.rename(new_name)
        except NotFound:
            raise DockerError(f"Container {old_name} not found")
        except DockerException as e:
            raise DockerError(f"Error renaming container {old_name} to {new_name}: {e}")
    
    def exec_command(self, container_name: str, command: str, workdir: Optional[str] = None) -> bool:
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
        try:
            container = self.client.containers.get(container_name)
            
            exec_result = container.exec_run(
                command, 
                workdir=workdir,
                tty=False,
                stream=False
            )
            
            return exec_result.exit_code == 0
            
        except NotFound:
            raise DockerError(f"Container {container_name} not found")
        except DockerException as e:
            raise DockerError(f"Error executing command in {container_name}: {e}")
    
    def get_image_creation_time(self, image_name: str) -> Optional[datetime]:
        """Get image creation time.
        
        Args:
            image_name: Image name or ID
            
        Returns:
            Image creation datetime, or None if not found
        """
        try:
            image = self.client.images.get(image_name)
            created_str = image.attrs['Created']
            # Parse Docker's ISO format (may have nanosecond precision on Linux)
            return _parse_docker_timestamp(created_str)
        except NotFound:
            return None
        except (DockerException, ValueError) as e:
            raise DockerError(f"Error getting image creation time for {image_name}: {e}")
    
    def find_images_by_pattern(self, pattern: str) -> List[str]:
        """Find images matching a name pattern.
        
        Args:
            pattern: Image name pattern to match
            
        Returns:
            List of matching image names
        """
        try:
            images = self.client.images.list()
            matching = []
            
            for image in images:
                if image.tags:
                    for tag in image.tags:
                        if pattern in tag:
                            matching.append(tag)
            
            return matching
            
        except DockerException as e:
            raise DockerError(f"Error finding images by pattern {pattern}: {e}")