"""Configuration management for webhook handler."""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    _has_dotenv = True
except ImportError:
    _has_dotenv = False


class WebhookConfig(BaseModel):
    """Configuration for the webhook handler."""
    
    # GitHub settings
    webhook_secret: str = Field(..., description="GitHub webhook secret")
    github_token: str = Field(..., description="GitHub personal access token")
    mentioned_user: str = Field(..., description="GitHub username to watch for @mentions")
    
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
    host: str = Field(default="0.0.0.0", description="Host to bind webhook server")
    port: int = Field(default=8000, description="Port to bind webhook server")
    webhook_path: str = Field(default="/webhook", description="Webhook endpoint path")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Logging format (json|console)")
    
    @classmethod
    def from_env(cls, dotenv_path: Optional[Path] = None) -> "WebhookConfig":
        """Create config from environment variables.
        
        Args:
            dotenv_path: Optional path to .env file to load
        """
        # Load .env file if available
        if _has_dotenv:
            if dotenv_path is None:
                # Look for .env in current directory and parent directories
                dotenv_path = Path.cwd()
                while dotenv_path != dotenv_path.parent:
                    env_file = dotenv_path / ".env"
                    if env_file.exists():
                        load_dotenv(env_file)
                        break
                    dotenv_path = dotenv_path.parent
            elif dotenv_path.exists():
                load_dotenv(dotenv_path)
        
        return cls(
            webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            mentioned_user=os.getenv("GITHUB_MENTIONED_USER", ""),
            container_pool=os.getenv("CONTAINER_POOL", "eamonn,harry,darren").split(","),
            container_timeout_minutes=int(os.getenv("CONTAINER_TIMEOUT_MINUTES", "30")),
            max_concurrent_tasks=int(os.getenv("MAX_CONCURRENT_TASKS", "3")),
            repo_cache_dir=Path(os.getenv("REPO_CACHE_DIR", Path.home() / ".devs-webhook" / "repos")),
            workspace_dir=Path(os.getenv("WORKSPACE_DIR", Path.home() / ".devs-webhook" / "workspaces")),
            host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            port=int(os.getenv("WEBHOOK_PORT", "8000")),
            webhook_path=os.getenv("WEBHOOK_PATH", "/webhook"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=os.getenv("LOG_FORMAT", "json"),
        )
    
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.repo_cache_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_required_settings(self) -> None:
        """Validate that required settings are present."""
        missing = []
        
        if not self.webhook_secret:
            missing.append("webhook_secret (GITHUB_WEBHOOK_SECRET)")
        if not self.github_token:
            missing.append("github_token (GITHUB_TOKEN)")
        if not self.mentioned_user:
            missing.append("mentioned_user (GITHUB_MENTIONED_USER)")
        

# Global config instance
_config: Optional[WebhookConfig] = None


def get_config(dotenv_path: Optional[Path] = None) -> WebhookConfig:
    """Get the global webhook configuration.
    
    Args:
        dotenv_path: Optional path to .env file to load
    """
    global _config
    if _config is None:
        _config = WebhookConfig.from_env(dotenv_path=dotenv_path)
        _config.validate_required_settings()
        _config.ensure_directories()
    return _config


def set_config(config: WebhookConfig) -> None:
    """Set the global webhook configuration."""
    global _config
    _config = config