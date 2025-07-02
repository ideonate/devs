"""CLI for webhook management."""

import asyncio
import click
import uvicorn
from pathlib import Path

from .config import get_config
from .app import app
from .utils.logging import setup_logging


@click.group()
def cli():
    """DevContainer Webhook Handler CLI."""
    pass


@cli.command()
@click.option('--host', default=None, help='Host to bind to')
@click.option('--port', default=None, type=int, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
@click.option('--env-file', type=click.Path(exists=True, path_type=Path), help='Path to .env file to load')
@click.option('--dev', is_flag=True, help='Development mode (auto-loads .env, enables reload, console logs)')
def serve(host: str, port: int, reload: bool, env_file: Path, dev: bool):
    """Start the webhook server.
    
    Examples:
        devs-webhook serve --dev                    # Development mode with .env loading
        devs-webhook serve --env-file /path/.env    # Load specific .env file
        devs-webhook serve --host 127.0.0.1        # Override host from config
    """
    setup_logging()
    
    # Handle development mode
    if dev:
        reload = True
        if env_file is None:
            # Look for .env in current directory
            env_file = Path.cwd() / ".env"
            if not env_file.exists():
                click.echo("⚠️  Development mode enabled but no .env file found")
                env_file = None
        
        click.echo("🚀 Development mode enabled")
        if env_file:
            click.echo(f"📄 Loading environment variables from {env_file}")
    
    # Load config with optional .env file  
    elif env_file:
        click.echo(f"📄 Loading environment variables from {env_file}")
    
    config = get_config(dotenv_path=env_file)
    
    # Override log format for development mode
    if dev:
        config.log_format = "console"
    
    # Override config with CLI options
    actual_host = host or config.host
    actual_port = port or config.port
    
    click.echo(f"Starting webhook server on {actual_host}:{actual_port}")
    click.echo(f"Watching for @{config.mentioned_user} mentions")
    click.echo(f"Container pool: {', '.join(config.container_pool)}")
    
    uvicorn.run(
        "devs_webhook.app:app",
        host=actual_host,
        port=actual_port,
        reload=reload,
        log_config=None,  # Use our structlog config
    )


@cli.command()
def status():
    """Show webhook handler status."""
    import httpx
    
    config = get_config()
    url = f"http://{config.host}:{config.port}/status"
    
    try:
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            
            click.echo("🟢 Webhook Handler Status")
            click.echo(f"Queued tasks: {data['queued_tasks']}")
            click.echo(f"Container pool size: {data['container_pool_size']}")
            click.echo(f"Mentioned user: @{data['mentioned_user']}")
            
            containers = data['containers']
            click.echo(f"\nContainers:")
            click.echo(f"  Available: {len(containers['available'])}")
            click.echo(f"  Busy: {len(containers['busy'])}")
            
            for name, info in containers['busy'].items():
                click.echo(f"    {name}: {info['repo']} (expires: {info['expires_at']})")
        else:
            click.echo(f"❌ Server returned {response.status_code}")
            
    except Exception as e:
        click.echo(f"❌ Failed to connect to webhook handler: {e}")


@cli.command()
def config():
    """Show current configuration."""
    try:
        config = get_config()
        
        click.echo("📋 Webhook Handler Configuration")
        click.echo(f"Mentioned user: @{config.mentioned_user}")
        click.echo(f"Container pool: {', '.join(config.container_pool)}")
        click.echo(f"Container timeout: {config.container_timeout_minutes} minutes")
        click.echo(f"Repository cache: {config.repo_cache_dir}")
        click.echo(f"Workspace directory: {config.workspace_dir}")
        click.echo(f"Server: {config.host}:{config.port}")
        click.echo(f"Webhook path: {config.webhook_path}")
        click.echo(f"Log level: {config.log_level}")
        
        # Check for missing required settings
        missing = []
        if not config.webhook_secret:
            missing.append("GITHUB_WEBHOOK_SECRET")
        if not config.github_token:
            missing.append("GITHUB_TOKEN")
        
        if missing:
            click.echo(f"\n⚠️  Missing required environment variables:")
            for var in missing:
                click.echo(f"   {var}")
        else:
            click.echo(f"\n✅ All required configuration present")
            
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}")


@cli.command()
@click.argument('container_name')
def stop_container(container_name: str):
    """Stop a specific container."""
    import httpx
    
    config = get_config()
    url = f"http://{config.host}:{config.port}/container/{container_name}/stop"
    
    try:
        response = httpx.post(url, timeout=10.0)
        if response.status_code == 200:
            click.echo(f"✅ Container {container_name} stopped")
        elif response.status_code == 404:
            click.echo(f"❌ Container {container_name} not found")
        else:
            click.echo(f"❌ Failed to stop container: {response.status_code}")
            
    except Exception as e:
        click.echo(f"❌ Failed to connect to webhook handler: {e}")


@cli.command()
def test_setup():
    """Test webhook handler setup and dependencies."""
    click.echo("🧪 Testing webhook handler setup...")
    
    # Test configuration
    try:
        config = get_config()
        click.echo("✅ Configuration loaded")
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}")
        return
    
    # Test directories
    try:
        config.ensure_directories()
        click.echo("✅ Directories created")
    except Exception as e:
        click.echo(f"❌ Directory creation failed: {e}")
        return
    
    # Test GitHub CLI
    try:
        import subprocess
        result = subprocess.run(['gh', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ GitHub CLI available")
        else:
            click.echo("❌ GitHub CLI not working")
    except FileNotFoundError:
        click.echo("❌ GitHub CLI not installed")
    
    # Test Docker
    try:
        import subprocess
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ Docker available")
        else:
            click.echo("❌ Docker not working")
    except FileNotFoundError:
        click.echo("❌ Docker not installed")
    
    # Test DevContainer CLI
    try:
        import subprocess
        result = subprocess.run(['devcontainer', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ DevContainer CLI available")
        else:
            click.echo("❌ DevContainer CLI not working")
    except FileNotFoundError:
        click.echo("❌ DevContainer CLI not installed")
    
    click.echo("\n🎉 Setup test complete!")


def main():
    """Main CLI entry point."""
    cli()


if __name__ == '__main__':
    main()