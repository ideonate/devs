"""Configuration management for devs package."""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Configuration settings for devs."""
    
    # Default settings
    PROJECT_PREFIX = "dev"
    WORKSPACES_DIR = Path.home() / ".devs" / "workspaces"
    CLAUDE_CONFIG_DIR = Path.home() / ".devs" / "claudeconfig"
    
    def __init__(self) -> None:
        """Initialize configuration with environment variable overrides."""
        self.project_prefix = os.getenv("DEVS_PROJECT_PREFIX", self.PROJECT_PREFIX)
        
        # Allow override of workspaces directory
        workspaces_env = os.getenv("DEVS_WORKSPACES_DIR")
        if workspaces_env:
            self.workspaces_dir = Path(workspaces_env)
        else:
            self.workspaces_dir = self.WORKSPACES_DIR
            
        # Allow override of Claude config directory  
        claude_config_env = os.getenv("DEVS_CLAUDE_CONFIG_DIR")
        if claude_config_env:
            self.claude_config_dir = Path(claude_config_env)
        else:
            self.claude_config_dir = self.CLAUDE_CONFIG_DIR
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.claude_config_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def container_labels(self) -> dict[str, str]:
        """Standard labels applied to containers."""
        return {
            "devs.managed": "true",
            "devs.version": "0.1.0",
        }


# Global config instance
config = Config()