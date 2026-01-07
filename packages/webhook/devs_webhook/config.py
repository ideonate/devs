"""Configuration management for webhook handler."""

import os
from pathlib import Path
from functools import lru_cache
from typing import List, Optional
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
    SettingsConfigDict = None
from pydantic import Field, model_validator
from devs_common.config import BaseConfig
import structlog


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
    
    # GitHub App settings (optional, for enhanced Checks API support)
    github_app_id: str = Field(default="", description="GitHub App ID for app authentication")
    github_app_private_key: str = Field(default="", description="GitHub App private key (PEM format) or path to private key file")
    github_app_installation_id: str = Field(default="", description="GitHub App installation ID (optional, can be auto-discovered)")
    
    # Access control settings
    allowed_orgs: str = Field(
        default="",
        description="Comma-separated list of allowed GitHub organizations"
    )
    allowed_users: str = Field(
        default="", 
        description="Comma-separated list of allowed GitHub usernames"
    )
    authorized_trigger_users: str = Field(
        default="",
        description="Comma-separated list of GitHub usernames authorized to trigger Claude dispatch"
    )
    authorized_ci_trigger_users: str = Field(
        default="",
        description="Comma-separated list of GitHub usernames authorized to trigger CI/test dispatch (can include the bot itself)"
    )
    
    # Basic auth settings for admin endpoints
    admin_username: str = Field(
        default="admin",
        description="Username for admin endpoint authentication"
    )
    admin_password: str = Field(
        default="",
        description="Password for admin endpoint authentication (required for production)"
    )
    
    # Runtime settings
    dev_mode: bool = Field(default=False, description="Development mode enabled")
    
    # Container pool settings
    container_pool: str = Field(
        default="eamonn,harry,darren",
        description="Comma-separated list of named containers in the pool"
    )
    container_timeout_minutes: int = Field(default=60, description="Container idle timeout in minutes")
    container_max_age_hours: int = Field(
        default=10,
        description="Maximum container age in hours (containers older than this are cleaned up when idle)"
    )
    cleanup_check_interval_seconds: int = Field(
        default=60,
        description="How often to check for idle/old containers (in seconds)"
    )
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

    # Codex settings (shared with CLI for interoperability)
    codex_config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs" / "codexconfig",
        description="Directory for Codex configuration (shared with CLI)"
    )
    
    # Server settings
    webhook_host: str = Field(default="0.0.0.0", description="Host to bind webhook server")
    webhook_port: int = Field(default=8000, description="Port to bind webhook server")
    webhook_path: str = Field(default="/webhook", description="Webhook endpoint path")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Logging format (json|console)")

    # Container output logging (CloudWatch-friendly)
    container_logs_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs" / "logs" / "webhook" / "containers",
        description="Directory for container output logs (CloudWatch agent compatible)"
    )
    container_logs_enabled: bool = Field(
        default=False,
        description="Enable writing container output to log files"
    )

    # Worker process logging (captures full worker subprocess logs)
    worker_logs_dir: Path = Field(
        default_factory=lambda: Path.home() / ".devs" / "logs" / "webhook" / "workers",
        description="Directory for worker subprocess logs"
    )
    worker_logs_enabled: bool = Field(
        default=True,
        description="Enable writing worker subprocess logs to files (recommended)"
    )

    # Task source configuration
    task_source: str = Field(
        default="webhook",
        description="Task source type: 'webhook' (FastAPI) or 'sqs' (AWS SQS polling)"
    )

    # AWS SQS configuration (only used when task_source='sqs')
    aws_sqs_queue_url: str = Field(
        default="",
        description="AWS SQS queue URL for receiving webhook events"
    )
    aws_sqs_dlq_url: str = Field(
        default="",
        description="AWS SQS dead-letter queue URL for failed messages"
    )
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for SQS"
    )
    sqs_wait_time_seconds: int = Field(
        default=20,
        description="SQS long polling wait time in seconds (1-20)"
    )

    # AWS S3 configuration for test artifact uploads (optional)
    aws_s3_artifact_bucket: str = Field(
        default="",
        description="AWS S3 bucket name for uploading test artifacts (optional)"
    )
    aws_s3_artifact_prefix: str = Field(
        default="devs-artifacts",
        description="S3 key prefix for uploaded artifacts"
    )
    aws_s3_artifact_base_url: str = Field(
        default="",
        description="Base URL for public artifact access (e.g., CloudFront distribution URL). "
                    "If set, artifact URLs will be shareable via this URL."
    )

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
        return [org.strip().lower() for org in self.allowed_orgs.split(',') if org.strip()]
    
    def get_allowed_users_list(self) -> List[str]:
        """Get allowed users as a list."""
        if not self.allowed_users:
            return []
        return [user.strip().lower() for user in self.allowed_users.split(',') if user.strip()]
    
    def get_authorized_trigger_users_list(self) -> List[str]:
        """Get authorized trigger users as a list (for Claude dispatch)."""
        if not self.authorized_trigger_users:
            return []
        return [user.strip().lower() for user in self.authorized_trigger_users.split(',') if user.strip()]

    def get_authorized_ci_trigger_users_list(self) -> List[str]:
        """Get authorized CI trigger users as a list (for test dispatch)."""
        if not self.authorized_ci_trigger_users:
            return []
        return [user.strip().lower() for user in self.authorized_ci_trigger_users.split(',') if user.strip()]
    
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
        # Codex config directory for container mounts
        self.codex_config_dir.mkdir(parents=True, exist_ok=True)
        # Container logs directory (if enabled)
        if self.container_logs_enabled:
            self.container_logs_dir.mkdir(parents=True, exist_ok=True)
        # Worker logs directory (if enabled)
        if self.worker_logs_enabled:
            self.worker_logs_dir.mkdir(parents=True, exist_ok=True)

    def validate_required_settings(self) -> None:
        """Validate that required settings are present."""
        missing = []

        # GitHub token and webhook secret are always required
        if not self.github_token:
            missing.append("github_token (GITHUB_TOKEN)")
        if not self.github_mentioned_user:
            missing.append("github_mentioned_user (GITHUB_MENTIONED_USER)")
        if not self.github_webhook_secret:
            missing.append("github_webhook_secret (GITHUB_WEBHOOK_SECRET) - required for signature verification")

        # Task source specific validations
        if self.task_source == "webhook":
            # Require admin password in production mode
            if not self.dev_mode and not self.admin_password:
                missing.append("admin_password (ADMIN_PASSWORD) - required in production mode")

        elif self.task_source == "sqs":
            # SQS source requires queue URL
            if not self.aws_sqs_queue_url:
                missing.append("aws_sqs_queue_url (AWS_SQS_QUEUE_URL) - required for SQS source")

        else:
            missing.append(f"task_source must be 'webhook' or 'sqs', got '{self.task_source}'")

        # Raise error if any required settings are missing
        if missing:
            raise ValueError(
                f"Missing required configuration:\n  " + "\n  ".join(missing)
            )
    
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

        # If no allowlist is configured, allow all repositories (backward compatibility)
        if not allowed_orgs and not allowed_users:
            return True

        # Check if owner is in allowed orgs or users
        return repo_owner.lower() in allowed_orgs or repo_owner.lower() in allowed_users
    
    def is_user_authorized_to_trigger(self, username: str) -> bool:
        """Check if a user is authorized to trigger Claude dispatch.

        Args:
            username: GitHub username that triggered the event

        Returns:
            True if user is authorized, False otherwise
        """
        authorized_users = self.get_authorized_trigger_users_list()

        # If no authorized users are configured, allow all (backward compatibility)
        if not authorized_users:
            return True

        # Check if the user is in the authorized list
        return username.lower() in authorized_users

    def is_user_authorized_for_ci(self, username: str) -> bool:
        """Check if a user is authorized to trigger CI/test dispatch.

        This is separate from Claude dispatch authorization because:
        - The bot itself should be able to trigger CI on its own PRs
        - CI triggers don't cause infinite loops like Claude dispatch might

        Args:
            username: GitHub username that triggered the event

        Returns:
            True if user is authorized, False otherwise
        """
        authorized_users = self.get_authorized_ci_trigger_users_list()

        # If no CI authorized users are configured, allow all (backward compatibility)
        if not authorized_users:
            return True

        # Check if the user is in the authorized list
        return username.lower() in authorized_users
    
    def get_default_workspaces_dir(self) -> Path:
        """Get default workspaces directory for webhook package."""
        return Path.home() / ".devs" / "workspaces"

    def get_default_bridge_dir(self) -> Path:
        """Get default bridge directory for webhook package."""
        return Path.home() / ".devs" / "bridge"

    def get_default_project_prefix(self) -> str:
        """Get default project prefix for webhook package."""
        return "dev"

    def has_s3_artifact_upload(self) -> bool:
        """Check if S3 artifact upload is configured.

        Returns:
            True if S3 bucket is configured for artifact uploads
        """
        return bool(self.aws_s3_artifact_bucket)

    def has_github_app_auth(self) -> bool:
        """Check if GitHub App authentication is configured.
        
        Returns:
            True if both app_id and private_key are provided
        """
        return bool(self.github_app_id and self.github_app_private_key)
    
    def get_github_app_private_key(self) -> str:
        """Get GitHub App private key content.
        
        If github_app_private_key is a file path, read the file.
        Otherwise, return the value directly as PEM content.
        
        Returns:
            Private key content in PEM format
        
        Raises:
            FileNotFoundError: If private key file doesn't exist
            ValueError: If private key is not configured
        """
        if not self.github_app_private_key:
            raise ValueError("GitHub App private key not configured")
        
        # If it looks like a file path, read the file
        if (self.github_app_private_key.startswith('/') or 
            self.github_app_private_key.startswith('~/') or
            '-----BEGIN' not in self.github_app_private_key):
            key_path = Path(self.github_app_private_key).expanduser()
            if not key_path.exists():
                raise FileNotFoundError(f"GitHub App private key file not found: {key_path}")
            return key_path.read_text()
        
        # Otherwise, treat as PEM content directly
        return self.github_app_private_key
    
    def create_github_app_auth(self, context: str = "") -> Optional["GitHubAppAuth"]:
        """Create a GitHubAppAuth instance if configuration is available.
        
        Args:
            context: Context string for logging (e.g., "webhook handler", "claude dispatcher")
            
        Returns:
            GitHubAppAuth instance if configured, None otherwise
        """
        if not self.has_github_app_auth():
            return None
            
        try:
            # Import here to avoid circular imports
            from .github.app_auth import GitHubAppAuth
            
            app_auth = GitHubAppAuth(
                app_id=self.github_app_id,
                private_key=self.get_github_app_private_key(),
                installation_id=self.github_app_installation_id if self.github_app_installation_id else None
            )
            
            logger = structlog.get_logger()
            logger.info("GitHub App authentication configured", context=context)
            return app_auth
            
        except Exception as e:
            logger = structlog.get_logger()
            logger.error("Failed to initialize GitHub App authentication", 
                        context=context, error=str(e))
            return None
        

@lru_cache()
def get_config() -> WebhookConfig:
    """Get the webhook configuration using FastAPI's recommended pattern."""
    config = WebhookConfig()
    config.ensure_directories()
    config.validate_required_settings()
    return config