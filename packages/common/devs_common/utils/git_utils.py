"""Git utility functions."""

from pathlib import Path
from typing import List, Optional

from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from ..exceptions import DevsError


def get_tracked_files(repo_dir: Path) -> List[Path]:
    """Get all files tracked by git (cached + others excluding gitignored).
    
    Args:
        repo_dir: Repository directory path
        
    Returns:
        List of tracked file paths relative to repo root
        
    Raises:
        DevsError: If git operations fail
    """
    try:
        repo = Repo(repo_dir)
        
        # Get cached (tracked) files
        cached_files = []
        for item in repo.index.entries.keys():
            cached_files.append(repo_dir / item[0])
        
        # Get other (untracked but not ignored) files
        other_files = []
        try:
            for item in repo.git.ls_files('--others', '--exclude-standard').splitlines():
                if item.strip():
                    other_files.append(repo_dir / item.strip())
        except GitCommandError:
            # If this fails, just use cached files
            pass
        
        return cached_files + other_files
        
    except (InvalidGitRepositoryError, GitCommandError) as e:
        raise DevsError(f"Git operation failed: {e}")


def is_git_repository(directory: Path) -> bool:
    """Check if directory is a git repository.
    
    Args:
        directory: Directory to check
        
    Returns:
        True if directory is a git repository
    """
    try:
        Repo(directory, search_parent_directories=False) 
        return True
    except InvalidGitRepositoryError:
        return False


def get_git_root(directory: Path) -> Optional[Path]:
    """Get git repository root directory.
    
    Args:
        directory: Directory to start search from
        
    Returns:
        Path to git root, or None if not in a git repository
    """
    try:
        repo = Repo(directory, search_parent_directories=True)
        return Path(repo.working_dir)
    except InvalidGitRepositoryError:
        return None


def is_devcontainer_gitignored(repo_dir: Path) -> bool:
    """Check if .devcontainer/ folder is gitignored in the repository.
    
    Args:
        repo_dir: Repository directory path
        
    Returns:
        True if .devcontainer/ is gitignored, False otherwise
        
    Raises:
        DevsError: If not a git repository
    """
    try:
        repo = Repo(repo_dir)
        
        # Check if .devcontainer/ is ignored using git check-ignore
        try:
            # If git check-ignore returns 0, the path is ignored
            repo.git.check_ignore('.devcontainer/')
            return True
        except GitCommandError:
            # If git check-ignore returns non-zero, the path is not ignored
            return False
            
    except InvalidGitRepositoryError:
        raise DevsError(f"{repo_dir} is not a git repository")