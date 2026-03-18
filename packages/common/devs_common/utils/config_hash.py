"""Utilities for computing configuration hashes for container invalidation."""

import hashlib
from pathlib import Path


def get_env_mount_path(project_name: str) -> Path:
    """Get the environment mount path for a project.

    Returns project-specific envs folder if it exists, otherwise default.

    Args:
        project_name: Project name in org-repo format (e.g., "ideonate-devs")

    Returns:
        Path to the envs folder that will be mounted
    """
    user_envs_dir = Path.home() / ".devs" / "envs"
    project_dir = user_envs_dir / project_name

    if project_dir.exists():
        return project_dir
    return user_envs_dir / "default"


def compute_env_config_hash(project_name: str) -> str:
    """Compute a hash of the environment configuration directory.

    This hash is used to detect when the envs folder has changed,
    which should trigger a container restart to pick up new environment variables.

    Uses the same logic as container mounting: project-specific folder if exists,
    otherwise default folder.

    Args:
        project_name: Project name in org-repo format (e.g., "ideonate-devs")

    Returns:
        Short hash string (first 12 chars of SHA256)
    """
    env_path = get_env_mount_path(project_name)
    return _hash_directory_contents(env_path)


def compute_devcontainer_hash(project_dir: Path) -> str:
    """Compute a content hash of devcontainer-related files.

    Uses file contents (not mtimes) so that fresh checkouts or rebases that
    don't change the actual devcontainer files produce the same hash.

    Args:
        project_dir: Root directory of the project

    Returns:
        Short hash string (first 12 chars of SHA256)
    """
    hasher = hashlib.sha256()

    devcontainer_paths = [
        project_dir / ".devcontainer",
        project_dir / "Dockerfile",
        project_dir / "docker-compose.yml",
        project_dir / "docker-compose.yaml",
    ]

    found_any = False
    try:
        for path in devcontainer_paths:
            if not path.exists():
                continue
            found_any = True
            if path.is_file():
                rel = path.relative_to(project_dir)
                hasher.update(str(rel).encode())
                hasher.update(path.read_bytes())
            elif path.is_dir():
                for item in sorted(path.rglob("*")):
                    if item.is_file():
                        rel = item.relative_to(project_dir)
                        hasher.update(str(rel).encode())
                        hasher.update(item.read_bytes())
    except (OSError, PermissionError):
        hasher.update(b"error")

    if not found_any:
        hasher.update(b"no-devcontainer")

    return hasher.hexdigest()[:12]


def _hash_directory_contents(directory: Path) -> str:
    """Hash the contents of all files in a directory.

    Uses file contents rather than mtimes so that fresh checkouts or rebases
    that don't change actual file content produce the same hash.

    Args:
        directory: Directory to hash

    Returns:
        Short hash string (first 12 chars of SHA256)
    """
    hasher = hashlib.sha256()

    if not directory.exists():
        hasher.update(b"missing")
        return hasher.hexdigest()[:12]

    # Include directory path in hash so different folders produce different hashes
    hasher.update(str(directory).encode())

    # Get all files sorted for consistency
    try:
        files = sorted(directory.rglob("*"))
        for file_path in files:
            if file_path.is_file():
                # Include relative path and file contents in hash
                rel_path = file_path.relative_to(directory)
                hasher.update(str(rel_path).encode())
                hasher.update(file_path.read_bytes())
    except (OSError, PermissionError):
        hasher.update(b"error")

    return hasher.hexdigest()[:12]
