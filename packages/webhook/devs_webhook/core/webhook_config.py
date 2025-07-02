"""Webhook-specific configuration extending the base config."""

from pathlib import Path
from devs_common.config import BaseConfig


class WebhookConfig(BaseConfig):
    """Configuration for webhook handler extending base config."""
    
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory - shared with CLI for interoperability."""
        return Path.home() / ".devs" / "workspaces"
    
    def get_default_project_prefix(self) -> str:
        """Get default project prefix - same as CLI for interoperability."""
        return "dev"