"""CLI for webhook management."""

import asyncio
import click
import uvicorn

from .config import get_config, WebhookConfig
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
def serve(host: str, port: int, reload: bool):
    """Start the webhook server."""
    setup_logging()
    
    config = get_config()
    
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
            click.echo(f"Active tasks: {data['active_tasks']}/{data['max_concurrent_tasks']}")
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
        click.echo(f"Max concurrent tasks: {config.max_concurrent_tasks}")
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
        if not config.claude_api_key:
            missing.append("CLAUDE_API_KEY")
        
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