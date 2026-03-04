"""Base configuration for devs ecosystem."""

import os
from pathlib import Path
from typing import Dict, Optional
from abc import ABC, abstractmethod


class BaseConfig(ABC):
    """Base configuration class for devs ecosystem packages."""
    
    # Default directories shared across CLI and webhook
    CLAUDE_CONFIG_DIR = Path.home() / ".devs" / "claudeconfig"
    CODEX_CONFIG_DIR = Path.home() / ".devs" / "codexconfig"
    VSCODE_CLI_DIR = Path.home() / ".devs" / "vscode-cli"

    def __init__(self) -> None:
        """Initialize base configuration."""
        self._workspaces_dir: Optional[Path] = None
        self._bridge_dir: Optional[Path] = None
        self._project_prefix: Optional[str] = None

        claude_config_env = os.getenv("DEVS_CLAUDE_CONFIG_DIR")
        self.claude_config_dir = Path(claude_config_env) if claude_config_env else self.CLAUDE_CONFIG_DIR

        codex_config_env = os.getenv("DEVS_CODEX_CONFIG_DIR")
        self.codex_config_dir = Path(codex_config_env) if codex_config_env else self.CODEX_CONFIG_DIR

        vscode_cli_env = os.getenv("DEVS_VSCODE_CLI_DIR")
        self.vscode_cli_dir = Path(vscode_cli_env) if vscode_cli_env else self.VSCODE_CLI_DIR
    
    @property
    def workspaces_dir(self) -> Path:
        """Get workspaces directory."""
        if self._workspaces_dir is None:
            # Default can be overridden by subclasses
            workspaces_env = os.getenv("DEVS_WORKSPACES_DIR")
            if workspaces_env:
                self._workspaces_dir = Path(workspaces_env)
            else:
                self._workspaces_dir = self.get_default_workspaces_dir()
        return self._workspaces_dir
    
    @workspaces_dir.setter
    def workspaces_dir(self, value: Path) -> None:
        """Set workspaces directory."""
        self._workspaces_dir = value
    
    @property
    def bridge_dir(self) -> Path:
        """Get bridge directory."""
        if self._bridge_dir is None:
            # Default can be overridden by subclasses
            bridge_env = os.getenv("DEVS_BRIDGE_DIR")
            if bridge_env:
                self._bridge_dir = Path(bridge_env)
            else:
                self._bridge_dir = self.get_default_bridge_dir()
        return self._bridge_dir
    
    @bridge_dir.setter
    def bridge_dir(self, value: Path) -> None:
        """Set bridge directory."""
        self._bridge_dir = value
    
    @property
    def project_prefix(self) -> str:
        """Get project prefix."""
        if self._project_prefix is None:
            self._project_prefix = os.getenv("DEVS_PROJECT_PREFIX", self.get_default_project_prefix())
        return self._project_prefix
    
    @project_prefix.setter
    def project_prefix(self, value: str) -> None:
        """Set project prefix."""
        self._project_prefix = value
    
    @abstractmethod
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory. Override in subclasses."""
        pass
    
    @abstractmethod
    def get_default_bridge_dir(self) -> Path:
        """Get default bridge directory. Override in subclasses."""
        pass
    
    @abstractmethod
    def get_default_project_prefix(self) -> str:
        """Get default project prefix. Override in subclasses."""
        pass
    
    @property
    def container_labels(self) -> Dict[str, str]:
        """Standard labels applied to containers."""
        return {
            "devs.managed": "true",
            "devs.version": "0.1.0",
        }
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self.claude_config_dir.mkdir(parents=True, exist_ok=True)
        self.codex_config_dir.mkdir(parents=True, exist_ok=True)
        self.vscode_cli_dir.mkdir(parents=True, exist_ok=True)