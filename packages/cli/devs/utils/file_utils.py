"""File operation utilities."""

import shutil
import stat
from pathlib import Path
from typing import List, Optional, Set

from ..exceptions import WorkspaceError


def copy_file_list(
    source_dir: Path,
    dest_dir: Path, 
    file_list: List[Path],
    preserve_permissions: bool = True
) -> None:
    """Copy a list of files from source to destination directory.
    
    Args:
        source_dir: Source directory
        dest_dir: Destination directory  
        file_list: List of file paths relative to source_dir
        preserve_permissions: Whether to preserve file permissions
        
    Raises:
        WorkspaceError: If copying fails
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path in file_list:
            if not file_path.exists():
                continue
                
            # Calculate relative path from source
            try:
                rel_path = file_path.relative_to(source_dir)
            except ValueError:
                # File is not under source_dir, skip
                continue
                
            dest_file = dest_dir / rel_path
            
            # Create parent directories
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            if file_path.is_file():
                shutil.copy2(file_path, dest_file)
                
                if preserve_permissions:
                    shutil.copystat(file_path, dest_file)
                    
    except (OSError, shutil.Error) as e:
        raise WorkspaceError(f"Failed to copy files: {e}")


def copy_directory_tree(
    source_dir: Path,
    dest_dir: Path,
    exclude_patterns: Optional[Set[str]] = None,
    preserve_permissions: bool = True
) -> None:
    """Copy entire directory tree with optional exclusions.
    
    Args:
        source_dir: Source directory
        dest_dir: Destination directory
        exclude_patterns: Set of glob patterns to exclude
        preserve_permissions: Whether to preserve permissions
        
    Raises:
        WorkspaceError: If copying fails
    """
    try:
        if not source_dir.exists():
            raise WorkspaceError(f"Source directory does not exist: {source_dir}")
        
        exclude_patterns = exclude_patterns or set()
        
        def ignore_patterns(directory: str, contents: List[str]) -> List[str]:
            """Ignore function for shutil.copytree."""
            ignored = []
            dir_path = Path(directory)
            
            for item in contents:
                item_path = dir_path / item
                
                # Check against exclude patterns
                for pattern in exclude_patterns:
                    if item_path.match(pattern):
                        ignored.append(item)
                        break
                        
            return ignored
        
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
            
        shutil.copytree(
            source_dir,
            dest_dir,
            ignore=ignore_patterns if exclude_patterns else None,
            copy_function=shutil.copy2 if preserve_permissions else shutil.copy
        )
        
    except (OSError, shutil.Error) as e:
        raise WorkspaceError(f"Failed to copy directory tree: {e}")


def safe_remove_directory(directory: Path) -> None:
    """Safely remove a directory and all its contents.
    
    Args:
        directory: Directory to remove
        
    Raises:
        WorkspaceError: If removal fails
    """
    try:
        if not directory.exists():
            return
            
        # Change permissions to allow deletion on all files
        def handle_remove_readonly(func, path, exc):
            """Error handler for rmtree to handle readonly files."""
            Path(path).chmod(stat.S_IWRITE)
            func(path)
        
        shutil.rmtree(directory, onerror=handle_remove_readonly)
        
    except (OSError, shutil.Error) as e:
        raise WorkspaceError(f"Failed to remove directory {directory}: {e}")


def ensure_directory_exists(directory: Path, mode: int = 0o755) -> None:
    """Ensure directory exists with proper permissions.
    
    Args:
        directory: Directory path to create
        mode: Directory permissions mode
        
    Raises:
        WorkspaceError: If directory creation fails
    """
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=mode)
    except OSError as e:
        raise WorkspaceError(f"Failed to create directory {directory}: {e}")


def get_directory_size(directory: Path) -> int:
    """Get total size of directory in bytes.
    
    Args:
        directory: Directory to measure
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for path in directory.rglob('*'):
            if path.is_file():
                total_size += path.stat().st_size
    except OSError:
        pass
    return total_size


def is_directory_empty(directory: Path) -> bool:
    """Check if directory is empty.
    
    Args:
        directory: Directory to check
        
    Returns:
        True if directory is empty or doesn't exist
    """
    if not directory.exists():
        return True
    
    try:
        return not any(directory.iterdir())
    except OSError:
        return True