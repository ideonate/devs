"""Configuration management for devs package."""

import os
from pathlib import Path
from typing import Dict, Optional

from devs_common.config import BaseConfig


class Config(BaseConfig):
    """Configuration settings for devs CLI."""

    # Default settings
    PROJECT_PREFIX = "dev"
    WORKSPACES_DIR = Path.home() / ".devs" / "workspaces"
    BRIDGE_DIR = Path.home() / ".devs" / "bridge"
    REPO_CACHE_DIR = Path.home() / ".devs" / "repocache"

    @property
    def container_labels(self) -> Dict[str, str]:
        """Standard labels applied to containers created by CLI."""
        labels = super().container_labels
        labels["devs.source"] = "cli"
        return labels

    def __init__(self) -> None:
        """Initialize configuration with environment variable overrides."""
        super().__init__()

        # CLI-specific configuration
        repo_cache_env = os.getenv("DEVS_REPO_CACHE_DIR")
        if repo_cache_env:
            self.repo_cache_dir = Path(repo_cache_env)
        else:
            self.repo_cache_dir = self.REPO_CACHE_DIR
    
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory for CLI package."""
        return self.WORKSPACES_DIR
    
    def get_default_bridge_dir(self) -> Path:
        """Get default bridge directory for CLI package."""
        return self.BRIDGE_DIR
    
    def get_default_project_prefix(self) -> str:
        """Get default project prefix for CLI package."""
        return self.PROJECT_PREFIX
    

# Global config instance
config = Config()