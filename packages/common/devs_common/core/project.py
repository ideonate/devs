"""Project detection and information management."""

import re
from pathlib import Path
from typing import Optional, NamedTuple
from urllib.parse import urlparse

from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from ..exceptions import DevcontainerConfigError, ProjectNotFoundError


class ProjectInfo(NamedTuple):
    """Container for project information."""
    directory: Path
    name: str
    git_remote_url: str
    hex_path: str
    is_git_repo: bool


class Project:
    """Handles project detection and information extraction."""
    
    def __init__(self, project_dir: Optional[Path] = None) -> None:
        """Initialize project with optional directory path.
        
        Args:
            project_dir: Project directory path. Defaults to current working directory.
        """
        self.project_dir = project_dir or Path.cwd()
        self._info: Optional[ProjectInfo] = None
    
    @property
    def info(self) -> ProjectInfo:
        """Get project information, computing it if not already cached."""
        if self._info is None:
            self._info = self._compute_project_info()
        return self._info
    
    def _compute_project_info(self) -> ProjectInfo:
        """Compute project information from directory and git repo."""
        project_dir = self.project_dir.resolve()

        # Require that this is a git repository
        project_name = ""
        git_remote_url = ""
        is_git_repo = False

        try:
            repo = Repo(project_dir, search_parent_directories=True)
            is_git_repo = True

            # Try to get remote URL
            if repo.remotes:
                origin = repo.remotes.origin if 'origin' in [r.name for r in repo.remotes] else repo.remotes[0]
                git_remote_url = origin.url
                project_name = self._extract_project_name_from_url(git_remote_url)

        except (InvalidGitRepositoryError, GitCommandError):
            # Not a git repo - raise an error
            raise ProjectNotFoundError(
                f"The directory '{project_dir}' is not a git repository.\n"
                "The 'devs' CLI requires a git repository to function properly.\n"
                "Please run this command from within a git repository."
            )

        # Fallback to directory name if no git remote URL
        if not project_name:
            project_name = project_dir.name.lower()

        # Generate hex path for VS Code integration
        hex_path = project_dir.as_posix().encode('utf-8').hex()

        return ProjectInfo(
            directory=project_dir,
            name=project_name,
            git_remote_url=git_remote_url,
            hex_path=hex_path,
            is_git_repo=is_git_repo
        )
    
    def _extract_project_name_from_url(self, git_url: str) -> str:
        """Extract org-repo format name from git URL.
        
        Args:
            git_url: Git remote URL
            
        Returns:
            Project name in org-repo format
        """
        # Handle different URL formats
        if git_url.startswith('git@'):
            # SSH format: git@github.com:org/repo.git
            match = re.search(r'git@[^:]+:(.+)', git_url)
            if match:
                path = match.group(1)
            else:
                return ""
        elif git_url.startswith('http'):
            # HTTPS format: https://github.com/org/repo.git
            parsed = urlparse(git_url)
            path = parsed.path.lstrip('/')
        else:
            return ""
        
        # Remove .git suffix and convert to lowercase
        if path.endswith('.git'):
            path = path[:-4]
        
        # Convert to org-repo format
        project_name = path.lower().replace('/', '-')
        
        return project_name
    
    def check_devcontainer_config(self) -> None:
        """Check if devcontainer configuration exists.
        
        Raises:
            DevcontainerConfigError: If devcontainer.json is not found
        """
        devcontainer_path = self.project_dir / ".devcontainer" / "devcontainer.json"
        if not devcontainer_path.exists():
            raise DevcontainerConfigError(
                f"No .devcontainer/devcontainer.json found in {self.project_dir}. "
                "Make sure you're in a project with devcontainer configuration."
            )
    
    def get_container_name(self, dev_name: str, prefix: str = "dev") -> str:
        """Generate container name for a dev environment.
        
        Args:
            dev_name: Development environment name
            prefix: Container name prefix
            
        Returns:
            Container name in format: prefix-project-devname
        """
        return f"{prefix}-{self.get_workspace_name(dev_name)}"
    
    def get_workspace_name(self, dev_name: str) -> str:
        """Generate workspace name for a dev environment.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Workspace name in format: org-repo-devname
        """
        return f"{self.info.name}-{dev_name}"