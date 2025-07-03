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
