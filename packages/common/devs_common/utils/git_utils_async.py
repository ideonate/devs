"""Async Git utility functions."""

import asyncio
from pathlib import Path
from typing import List, Optional, Tuple

from ..exceptions import DevsError


async def run_git_command(
    repo_dir: Path,
    args: List[str],
    timeout: float = 30.0
) -> Tuple[bool, str, str]:
    """Run a git command asynchronously.
    
    Args:
        repo_dir: Repository directory
        args: Git command arguments
        timeout: Command timeout in seconds
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    cmd = ["git", "-C", str(repo_dir)] + args
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return False, "", f"Git command timed out after {timeout} seconds"
        
        return (
            process.returncode == 0,
            stdout.decode('utf-8', errors='replace') if stdout else "",
            stderr.decode('utf-8', errors='replace') if stderr else ""
        )
        
    except Exception as e:
        return False, "", str(e)


async def get_tracked_files_async(repo_dir: Path) -> List[Path]:
    """Get all files tracked by git (cached + others excluding gitignored).
    
    Args:
        repo_dir: Repository directory path
        
    Returns:
        List of tracked file paths relative to repo root
        
    Raises:
        DevsError: If git operations fail
    """
    tracked_files = []
    
    # Get cached (tracked) files
    success, stdout, stderr = await run_git_command(
        repo_dir,
        ["ls-files", "--cached"]
    )
    
    if not success:
        raise DevsError(f"Failed to get tracked files: {stderr}")
    
    for line in stdout.splitlines():
        if line.strip():
            tracked_files.append(repo_dir / line.strip())
    
    # Get other (untracked but not ignored) files
    success, stdout, stderr = await run_git_command(
        repo_dir,
        ["ls-files", "--others", "--exclude-standard"]
    )
    
    if success:
        for line in stdout.splitlines():
            if line.strip():
                tracked_files.append(repo_dir / line.strip())
    
    return tracked_files


async def is_git_repository_async(directory: Path) -> bool:
    """Check if directory is a git repository.
    
    Args:
        directory: Directory to check
        
    Returns:
        True if directory is a git repository
    """
    success, _, _ = await run_git_command(
        directory,
        ["rev-parse", "--git-dir"],
        timeout=5.0
    )
    return success


async def get_git_root_async(directory: Path) -> Optional[Path]:
    """Get git repository root directory.
    
    Args:
        directory: Directory to start search from
        
    Returns:
        Path to git root, or None if not in a git repository
    """
    success, stdout, _ = await run_git_command(
        directory,
        ["rev-parse", "--show-toplevel"],
        timeout=5.0
    )
    
    if success and stdout.strip():
        return Path(stdout.strip())
    return None


async def get_remote_url_async(repo_dir: Path) -> Optional[str]:
    """Get the remote URL for the repository.
    
    Args:
        repo_dir: Repository directory
        
    Returns:
        Remote URL or None if not found
    """
    success, stdout, _ = await run_git_command(
        repo_dir,
        ["config", "--get", "remote.origin.url"]
    )
    
    if success and stdout.strip():
        return stdout.strip()
    return None


async def get_current_branch_async(repo_dir: Path) -> Optional[str]:
    """Get the current branch name.
    
    Args:
        repo_dir: Repository directory
        
    Returns:
        Branch name or None if not on a branch
    """
    success, stdout, _ = await run_git_command(
        repo_dir,
        ["rev-parse", "--abbrev-ref", "HEAD"]
    )
    
    if success and stdout.strip():
        branch = stdout.strip()
        return branch if branch != "HEAD" else None
    return None


async def clone_repository_async(
    url: str,
    target_dir: Path,
    branch: Optional[str] = None,
    depth: Optional[int] = None
) -> bool:
    """Clone a git repository asynchronously.
    
    Args:
        url: Repository URL
        target_dir: Target directory for clone
        branch: Specific branch to clone
        depth: Clone depth (for shallow clones)
        
    Returns:
        True if successful
    """
    cmd = ["git", "clone"]
    
    if branch:
        cmd.extend(["--branch", branch])
    
    if depth:
        cmd.extend(["--depth", str(depth)])
    
    cmd.extend([url, str(target_dir)])
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=120.0  # Clone can take a while
        )
        
        return process.returncode == 0
        
    except asyncio.TimeoutError:
        return False
    except Exception:
        return False