"""Compatibility between devs-webhook's config and newer devs-common releases."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

from devs_common.config import BaseConfig


class OlderWebhookConfig(BaseSettings, BaseConfig):
    """Shaped like a devs-webhook WebhookConfig released before Hermes support."""

    def __init__(self, **kwargs):
        BaseSettings.__init__(self, **kwargs)
        BaseConfig.__init__(self)

    claude_config_dir: Path = Field(default_factory=lambda: Path.home() / ".devs" / "claudeconfig")
    codex_config_dir: Path = Field(default_factory=lambda: Path.home() / ".devs" / "codexconfig")

    def get_default_workspaces_dir(self) -> Path:
        return Path.home() / ".devs" / "workspaces"

    def get_default_bridge_dir(self) -> Path:
        return Path.home() / ".devs" / "bridge"

    def get_default_project_prefix(self) -> str:
        return "dev"


def test_older_webhook_config_gets_hermes_dir(tmp_path, monkeypatch):
    """A config without a hermes_config_dir field still constructs and creates the dir."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(BaseConfig, "HERMES_CONFIG_DIR", tmp_path / ".devs" / "hermesconfig")

    config = OlderWebhookConfig()
    config.ensure_directories()

    assert config.hermes_config_dir == tmp_path / ".devs" / "hermesconfig"
    assert config.hermes_config_dir.is_dir()
