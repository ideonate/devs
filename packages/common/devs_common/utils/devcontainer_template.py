"""DevContainer template utilities."""

import shutil
from pathlib import Path
from typing import Optional
import pkg_resources

from ..exceptions import WorkspaceError


def get_template_dir() -> Path:
    """Get the path to devcontainer templates.
    
    Returns:
        Path to template directory
    """
    try:
        # Get the package path
        import devs_common
        package_path = Path(devs_common.__file__).parent
        return package_path / "templates"
    except Exception:
        raise WorkspaceError("Could not locate devcontainer templates")


def has_devcontainer_config(project_dir: Path) -> bool:
    """Check if project has its own devcontainer configuration.
    
    Args:
        project_dir: Project directory path
        
    Returns:
        True if project has devcontainer config
    """
    devcontainer_dir = project_dir / ".devcontainer"
    devcontainer_file = devcontainer_dir / "devcontainer.json"
    
    return devcontainer_file.exists()


def copy_default_devcontainer(workspace_dir: Path) -> None:
    """Copy default devcontainer template to workspace.
    
    Args:
        workspace_dir: Workspace directory path
        
    Raises:
        WorkspaceError: If template copying fails
    """
    try:
        template_dir = get_template_dir()
        target_dir = workspace_dir / ".devcontainer"
        
        # Create .devcontainer directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all template files from the templates directory
        # This includes both config files (devcontainer.json, Dockerfile) 
        # and script files that will be copied during Docker build
        for template_file in template_dir.iterdir():
            if template_file.is_file():
                dest = target_dir / template_file.name
                shutil.copy2(template_file, dest)
        
        # Create .dockerignore if it doesn't exist
        dockerignore = workspace_dir / ".dockerignore"
        if not dockerignore.exists():
            dockerignore.write_text("""
node_modules
.git
.env
.env.local
.env.*.local
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.DS_Store
*.log
.pytest_cache
__pycache__
.coverage
.mypy_cache
.tox
""".strip())
                
    except Exception as e:
        raise WorkspaceError(f"Failed to copy devcontainer template: {e}")


def ensure_devcontainer_config(workspace_dir: Path, project_dir: Path) -> bool:
    """Ensure workspace has devcontainer configuration.
    
    Args:
        workspace_dir: Workspace directory path  
        project_dir: Original project directory path
        
    Returns:
        True if devcontainer config is available
        
    Raises:
        WorkspaceError: If devcontainer setup fails
    """
    # Check if project already has devcontainer config
    if has_devcontainer_config(project_dir):
        # Project has its own config, it should already be copied to workspace
        return True
    
    # Check if workspace already has devcontainer config  
    if has_devcontainer_config(workspace_dir):
        return True
    
    # Copy default template
    copy_default_devcontainer(workspace_dir)
    return True