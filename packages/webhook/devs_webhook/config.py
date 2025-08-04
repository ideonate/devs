"""Configuration management for webhook handler."""

import os
from pathlib import Path
from typing import List
from functools import lru_cache
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
    SettingsConfigDict = None
from pydantic import Field, model_validator
from devs_common.config import BaseConfig


class WebhookConfig(BaseSettings, BaseConfig):
    """Configuration for the webhook handler."""
    
    def __init__(self, **kwargs):
        """Initialize webhook configuration with both BaseSettings and BaseConfig."""
        BaseSettings.__init__(self, **kwargs)
        BaseConfig.__init__(self)
    
    # GitHub settings
    github_webhook_secret: str = Field(default="", description="GitHub webhook secret")
    github_token: str = Field(default="", description="GitHub personal access token")
    github_mentioned_user: str = Field(default="", description="GitHub username to watch for @mentions")
    
    # Access control settings
    allowed_orgs: str = Field(
        default="",
        description="Comma-separated list of allowed GitHub organizations"
    )
    allowed_users: str = Field(
        default="", 
        description="Comma-separated list of allowed GitHub usernames"
    )
    
    # Runtime settings
    dev_mode: bool = Field(default=False, description="Development mode enabled")
    
    # Container pool settings
    container_pool: str = Field(
        default="eamonn,harry,darren",
        description="Comma-separated list of named containers in the pool"
    )
    container_timeout_minutes: int = Field(default=30, description="Container timeout in minutes")
    max_concurrent_tasks: int = Field(default=3, description="Maximum concurrent tasks")
    
    # Repository settings
    repo_cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs" / "repocache",
        description="Directory to cache cloned repositories (shared with CLI)"
    )
    
    # Claude Code settings (shared with CLI for interoperability)
    claude_config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs" / "claudeconfig",
        description="Directory for Claude Code configuration (shared with CLI)"
    )
    
    # Server settings
    webhook_host: str = Field(default="0.0.0.0", description="Host to bind webhook server")
    webhook_port: int = Field(default=8000, description="Port to bind webhook server")
    webhook_path: str = Field(default="/webhook", description="Webhook endpoint path")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Logging format (json|console)")
    
    @model_validator(mode='after')
    def adjust_dev_mode_defaults(self):
        """Adjust defaults based on dev_mode."""
        if self.dev_mode:
            if self.webhook_host == "0.0.0.0":
                self.webhook_host = "127.0.0.1"
            if self.log_format == "json":
                self.log_format = "console"
        return self
    
    # Configuration for Pydantic Settings
    # Note: .env files are optional - environment variables are the primary source
    if SettingsConfigDict:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            env_ignore_empty=True  # Ignore empty .env values, prefer environment
        )
    
    def get_allowed_orgs_list(self) -> List[str]:
        """Get allowed orgs as a list."""
        if not self.allowed_orgs:
            return []
        return [org.strip() for org in self.allowed_orgs.split(',') if org.strip()]
    
    def get_allowed_users_list(self) -> List[str]:
        """Get allowed users as a list."""
        if not self.allowed_users:
            return []
        return [user.strip() for user in self.allowed_users.split(',') if user.strip()]
    
    def get_container_pool_list(self) -> List[str]:
        """Get container pool as a list."""
        if not self.container_pool:
            return ["eamonn", "harry", "darren"]  # Default fallback
        return [container.strip() for container in self.container_pool.split(',') if container.strip()]
    
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        # Call parent's ensure_directories (creates workspaces_dir)
        super().ensure_directories()
        # Create webhook-specific directories
        self.repo_cache_dir.mkdir(parents=True, exist_ok=True)
        # Claude config directory for container mounts
        self.claude_config_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_required_settings(self) -> None:
        """Validate that required settings are present."""
        missing = []
        
        if not self.github_webhook_secret:
            missing.append("github_webhook_secret (GITHUB_WEBHOOK_SECRET)")
        if not self.github_token:
            missing.append("github_token (GITHUB_TOKEN)")
        if not self.github_mentioned_user:
            missing.append("github_mentioned_user (GITHUB_MENTIONED_USER)")
    
    def is_repository_allowed(self, repo_full_name: str, repo_owner: str) -> bool:
        """Check if a repository is allowed based on allowlist configuration.
        
        Args:
            repo_full_name: Full repository name (e.g., "owner/repo")
            repo_owner: Repository owner username or organization
            
        Returns:
            True if repository is allowed, False otherwise
        """
        allowed_orgs = self.get_allowed_orgs_list()
        allowed_users = self.get_allowed_users_list()
        
        # Check if owner is in allowed orgs or users
        return repo_owner in allowed_orgs or repo_owner in allowed_users
    
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory for webhook package."""
        return Path.home() / ".devs" / "workspaces"
    
    def get_default_project_prefix(self) -> str:
        """Get default project prefix for webhook package."""
        return "dev"
        

@lru_cache()
def get_config() -> WebhookConfig:
    """Get the webhook configuration using FastAPI's recommended pattern."""
    config = WebhookConfig()
    config.ensure_directories()
    config.validate_required_settings()
    return config