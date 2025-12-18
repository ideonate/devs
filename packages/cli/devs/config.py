"""Configuration management for devs package."""

import os
from pathlib import Path
from typing import Optional

from devs_common.config import BaseConfig


class Config(BaseConfig):
    """Configuration settings for devs CLI."""
    
    # Default settings
    PROJECT_PREFIX = "dev"
    WORKSPACES_DIR = Path.home() / ".devs" / "workspaces"
    BRIDGE_DIR = Path.home() / ".devs" / "bridge"
    CLAUDE_CONFIG_DIR = Path.home() / ".devs" / "claudeconfig"
    CODEX_CONFIG_DIR = Path.home() / ".devs" / "codexconfig"

    def __init__(self) -> None:
        """Initialize configuration with environment variable overrides."""
        super().__init__()

        # CLI-specific configuration
        claude_config_env = os.getenv("DEVS_CLAUDE_CONFIG_DIR")
        if claude_config_env:
            self.claude_config_dir = Path(claude_config_env)
        else:
            self.claude_config_dir = self.CLAUDE_CONFIG_DIR

        codex_config_env = os.getenv("DEVS_CODEX_CONFIG_DIR")
        if codex_config_env:
            self.codex_config_dir = Path(codex_config_env)
        else:
            self.codex_config_dir = self.CODEX_CONFIG_DIR
    
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory for CLI package."""
        return self.WORKSPACES_DIR
    
    def get_default_bridge_dir(self) -> Path:
        """Get default bridge directory for CLI package."""
        return self.BRIDGE_DIR
    
    def get_default_project_prefix(self) -> str:
        """Get default project prefix for CLI package."""
        return self.PROJECT_PREFIX
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        super().ensure_directories()
        self.claude_config_dir.mkdir(parents=True, exist_ok=True)
        self.codex_config_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()