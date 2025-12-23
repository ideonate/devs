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
    return _hash_directory_mtimes(env_path)


def _hash_directory_mtimes(directory: Path) -> str:
    """Hash mtimes of all files in a directory.

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
                # Include relative path and mtime in hash
                rel_path = file_path.relative_to(directory)
                mtime = file_path.stat().st_mtime
                hasher.update(f"{rel_path}:{mtime}".encode())
    except (OSError, PermissionError):
        hasher.update(b"error")

    return hasher.hexdigest()[:12]
