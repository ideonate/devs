"""Configuration for webadmin package."""

import os
from pathlib import Path
from typing import Dict

from devs_common.config import BaseConfig


class WebAdminConfig(BaseConfig):
    """Configuration settings for devs web admin."""

    PROJECT_PREFIX = "dev"
    WORKSPACES_DIR = Path.home() / ".devs" / "workspaces"
    BRIDGE_DIR = Path.home() / ".devs" / "bridge"
    REPO_CACHE_DIR = Path.home() / ".devs" / "repocache"

    def __init__(self) -> None:
        super().__init__()

        repo_cache_env = os.getenv("DEVS_REPO_CACHE_DIR")
        self.repo_cache_dir = Path(repo_cache_env) if repo_cache_env else self.REPO_CACHE_DIR

        self.host = os.getenv("WEBADMIN_HOST", "0.0.0.0")
        self.port = int(os.getenv("WEBADMIN_PORT", "8080"))

    @property
    def container_labels(self) -> Dict[str, str]:
        labels = super().container_labels
        labels["devs.source"] = "webadmin"
        return labels

    def get_default_workspaces_dir(self) -> Path:
        return self.WORKSPACES_DIR

    def get_default_bridge_dir(self) -> Path:
        return self.BRIDGE_DIR

    def get_default_project_prefix(self) -> str:
        return self.PROJECT_PREFIX


config = WebAdminConfig()
