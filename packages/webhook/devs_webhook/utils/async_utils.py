"""Async utilities for non-blocking operations."""

import asyncio
import subprocess
from typing import Optional, Tuple
import structlog

logger = structlog.get_logger()


async def run_subprocess_async(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: Optional[float] = None
) -> Tuple[int, str, str]:
    """Run a subprocess asynchronously without blocking the event loop.
    
    Args:
        cmd: Command and arguments to run
        cwd: Working directory
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        # Create subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        # Wait for completion with optional timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return -1, "", f"Command timed out after {timeout} seconds"
        
        return (
            process.returncode or 0,
            stdout.decode('utf-8', errors='replace') if stdout else "",
            stderr.decode('utf-8', errors='replace') if stderr else ""
        )
        
    except Exception as e:
        logger.error("Subprocess execution failed",
                    cmd=cmd,
                    error=str(e))
        return -1, "", str(e)


async def run_git_async(
    args: list[str],
    cwd: str,
    timeout: float = 30.0
) -> Tuple[bool, str, str]:
    """Run a git command asynchronously.
    
    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    cmd = ["git"] + args
    returncode, stdout, stderr = await run_subprocess_async(cmd, cwd, timeout)
    
    success = returncode == 0
    
    if not success:
        logger.debug("Git command failed",
                    args=args,
                    cwd=cwd,
                    returncode=returncode,
                    stderr=stderr)
    
    return success, stdout, stderr