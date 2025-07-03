"""DevContainer template utilities."""

from pathlib import Path

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
