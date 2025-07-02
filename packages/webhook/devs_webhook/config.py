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

try:
    from dotenv import load_dotenv
    _has_dotenv = True
except ImportError:
    _has_dotenv = False


class WebhookConfig(BaseSettings):
    """Configuration for the webhook handler."""
    
    # GitHub settings
    github_webhook_secret: str = Field(default="", description="GitHub webhook secret")
    github_token: str = Field(default="", description="GitHub personal access token")
    github_mentioned_user: str = Field(default="", description="GitHub username to watch for @mentions")
    
    # Runtime settings (not from env)
    dev_mode: bool = Field(default=False, description="Development mode enabled")
    
    # Container pool settings
    container_pool: List[str] = Field(
        default_factory=lambda: ["eamonn", "harry", "darren"],
        description="Named containers in the pool"
    )
    container_timeout_minutes: int = Field(default=30, description="Container timeout in minutes")
    max_concurrent_tasks: int = Field(default=3, description="Maximum concurrent tasks")
    
    # Repository settings
    repo_cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs-webhook" / "repos",
        description="Directory to cache repositories"
    )
    workspace_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs-webhook" / "workspaces", 
        description="Directory for container workspaces"
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
    if SettingsConfigDict:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False
        )
    
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.repo_cache_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_required_settings(self) -> None:
        """Validate that required settings are present."""
        missing = []
        
        if not self.github_webhook_secret:
            missing.append("github_webhook_secret (GITHUB_WEBHOOK_SECRET)")
        if not self.github_token:
            missing.append("github_token (GITHUB_TOKEN)")
        if not self.github_mentioned_user:
            missing.append("github_mentioned_user (GITHUB_MENTIONED_USER)")
        

@lru_cache()
def get_config() -> WebhookConfig:
    """Get the webhook configuration using FastAPI's recommended pattern."""
    config = WebhookConfig()
    config.ensure_directories()
    config.validate_required_settings()
    return config