"""Async file operation utilities."""

import asyncio
import aiofiles
import aiofiles.os
import stat
from pathlib import Path
from typing import List, Optional, Set

from ..exceptions import WorkspaceError


async def copy_file_async(source: Path, dest: Path, preserve_permissions: bool = True) -> None:
    """Copy a single file asynchronously.
    
    Args:
        source: Source file path
        dest: Destination file path
        preserve_permissions: Whether to preserve file permissions
        
    Raises:
        WorkspaceError: If copying fails
    """
    try:
        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file content
        async with aiofiles.open(source, 'rb') as src_file:
            async with aiofiles.open(dest, 'wb') as dst_file:
                while chunk := await src_file.read(1024 * 1024):  # 1MB chunks
                    await dst_file.write(chunk)
        
        # Copy permissions if requested
        if preserve_permissions:
            stats = await aiofiles.os.stat(source)
            await aiofiles.os.chmod(dest, stat.S_IMODE(stats.st_mode))
            
    except Exception as e:
        raise WorkspaceError(f"Failed to copy file {source} to {dest}: {e}")


async def copy_file_list_async(
    source_dir: Path,
    dest_dir: Path, 
    file_list: List[Path],
    preserve_permissions: bool = True
) -> None:
    """Copy a list of files from source to destination directory asynchronously.
    
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
        
        # Create tasks for copying files concurrently
        tasks = []
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
            
            # Only copy files (directories are created as needed)
            if file_path.is_file():
                tasks.append(copy_file_async(file_path, dest_file, preserve_permissions))
        
        # Execute all copy operations concurrently
        if tasks:
            await asyncio.gather(*tasks)
                    
    except Exception as e:
        raise WorkspaceError(f"Failed to copy files: {e}")


async def remove_directory_async(directory: Path) -> None:
    """Asynchronously remove a directory and all its contents.
    
    Args:
        directory: Directory to remove
        
    Raises:
        WorkspaceError: If removal fails
    """
    try:
        if not directory.exists():
            return
        
        # Use asyncio to run rm -rf in subprocess for efficiency
        process = await asyncio.create_subprocess_exec(
            "rm", "-rf", str(directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise WorkspaceError(
                f"Failed to remove directory {directory}: {stderr.decode('utf-8')}"
            )
            
    except Exception as e:
        raise WorkspaceError(f"Failed to remove directory {directory}: {e}")


async def copy_directory_tree_async(
    source_dir: Path,
    dest_dir: Path,
    exclude_patterns: Optional[Set[str]] = None,
    preserve_permissions: bool = True
) -> None:
    """Copy entire directory tree asynchronously with optional exclusions.
    
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
        
        # Remove destination if it exists
        if dest_dir.exists():
            await remove_directory_async(dest_dir)
        
        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Walk through source directory and copy files
        tasks = []
        for item in source_dir.rglob('*'):
            # Check exclusions
            excluded = False
            for pattern in exclude_patterns:
                if item.match(pattern):
                    excluded = True
                    break
            
            if excluded:
                continue
            
            rel_path = item.relative_to(source_dir)
            dest_path = dest_dir / rel_path
            
            if item.is_file():
                tasks.append(copy_file_async(item, dest_path, preserve_permissions))
            elif item.is_dir():
                # Create directory
                dest_path.mkdir(parents=True, exist_ok=True)
        
        # Execute all copy operations concurrently
        if tasks:
            # Limit concurrency to avoid too many open files
            semaphore = asyncio.Semaphore(100)
            
            async def limited_copy(task):
                async with semaphore:
                    await task
            
            await asyncio.gather(*[limited_copy(task) for task in tasks])
        
    except Exception as e:
        raise WorkspaceError(f"Failed to copy directory tree: {e}")


async def get_directory_size_async(directory: Path) -> int:
    """Get total size of directory in bytes asynchronously.
    
    Args:
        directory: Directory to measure
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        # Use du command for efficiency
        process = await asyncio.create_subprocess_exec(
            "du", "-sb", str(directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        
        if process.returncode == 0 and stdout:
            # du -sb output format: "size\tpath"
            size_str = stdout.decode('utf-8').split('\t')[0]
            total_size = int(size_str)
    except Exception:
        # Fallback to manual calculation
        try:
            for path in directory.rglob('*'):
                if path.is_file():
                    stats = await aiofiles.os.stat(path)
                    total_size += stats.st_size
        except Exception:
            pass
    
    return total_size


async def is_directory_empty_async(directory: Path) -> bool:
    """Check if directory is empty asynchronously.
    
    Args:
        directory: Directory to check
        
    Returns:
        True if directory is empty or doesn't exist
    """
    if not directory.exists():
        return True
    
    try:
        # Use ls to check if directory is empty
        process = await asyncio.create_subprocess_exec(
            "ls", "-A", str(directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        
        return len(stdout.strip()) == 0
    except Exception:
        return True


async def ensure_directory_exists_async(directory: Path, mode: int = 0o755) -> None:
    """Ensure directory exists with proper permissions asynchronously.
    
    Args:
        directory: Directory path to create
        mode: Directory permissions mode
        
    Raises:
        WorkspaceError: If directory creation fails
    """
    try:
        # Create directory using asyncio executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: directory.mkdir(parents=True, exist_ok=True, mode=mode)
        )
    except OSError as e:
        raise WorkspaceError(f"Failed to create directory {directory}: {e}")