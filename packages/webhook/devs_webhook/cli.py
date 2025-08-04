"""CLI for webhook management."""

import click
import uvicorn
from pathlib import Path

from .config import get_config
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
    
    # Set environment variables for FastAPI app
    import os
    if dev:
        os.environ["DEV_MODE"] = "true"
        os.environ["LOG_FORMAT"] = "console"
        os.environ["WEBHOOK_HOST"] = "127.0.0.1"
    if env_file:
        # Load the env file explicitly
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            click.echo("⚠️ python-dotenv not available, skipping .env file loading")
    
    # Get config for display purposes
    config = get_config()
    
    # Override config with CLI options  
    actual_host = host or config.webhook_host
    actual_port = port or config.webhook_port
    
    click.echo(f"Starting webhook server on {actual_host}:{actual_port}")
    click.echo(f"Watching for @{config.github_mentioned_user} mentions")
    click.echo(f"Container pool: {', '.join(config.get_container_pool_list())}")
    if dev:
        click.echo("🔧 Development mode enabled - /testevent endpoint available")
    
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
    url = f"http://{config.webhook_host}:{config.webhook_port}/status"
    
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
        click.echo(f"Mentioned user: @{config.github_mentioned_user}")
        click.echo(f"Container pool: {', '.join(config.get_container_pool_list())}")
        click.echo(f"Container timeout: {config.container_timeout_minutes} minutes")
        click.echo(f"Repository cache: {config.repo_cache_dir}")
        click.echo(f"Workspace directory: {config.workspace_dir}")
        click.echo(f"Server: {config.webhook_host}:{config.webhook_port}")
        click.echo(f"Webhook path: {config.webhook_path}")
        click.echo(f"Log level: {config.log_level}")
        
        # Check for missing required settings
        missing = []
        if not config.github_webhook_secret:
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
    url = f"http://{config.webhook_host}:{config.webhook_port}/container/{container_name}/stop"
    
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


@cli.command()
@click.argument('prompt')
@click.option('--repo', default='test/repo', help='Repository name (default: test/repo)')
@click.option('--host', default=None, help='Webhook server host')
@click.option('--port', default=None, type=int, help='Webhook server port')
def test(prompt: str, repo: str, host: str, port: int):
    """Send a test prompt to the webhook handler.
    
    This sends a test event to the /testevent endpoint, which is only available
    in development mode.
    
    Examples:
        devs-webhook test "Fix the login bug"
        devs-webhook test "Add dark mode toggle" --repo myorg/myproject
    """
    import httpx
    
    config = get_config()
    
    # Use CLI options or config defaults
    actual_host = host or config.webhook_host
    actual_port = port or config.webhook_port
    url = f"http://{actual_host}:{actual_port}/testevent"
    
    payload = {
        "prompt": prompt,
        "repo": repo
    }
    
    try:
        click.echo(f"🧪 Sending test event to {url}")
        click.echo(f"📝 Prompt: {prompt}")
        click.echo(f"📦 Repository: {repo}")
        
        response = httpx.post(
            url,
            json=payload,
            timeout=10.0
        )
        
        if response.status_code == 202:
            data = response.json()
            click.echo(f"\n✅ Test event accepted!")
            click.echo(f"🆔 Delivery ID: {data['delivery_id']}")
            click.echo(f"📋 Status: {data['status']}")
            click.echo(f"\n💡 Check logs or /status endpoint for processing updates")
            
        elif response.status_code == 404:
            click.echo(f"❌ Test endpoint not available (server not in development mode)")
            click.echo(f"💡 Start server with: devs-webhook serve --dev")
            
        else:
            click.echo(f"❌ Request failed with status {response.status_code}")
            try:
                error_data = response.json()
                click.echo(f"Error: {error_data.get('detail', 'Unknown error')}")
            except:
                click.echo(f"Response: {response.text}")
                
    except httpx.ConnectError:
        click.echo(f"❌ Failed to connect to webhook server at {actual_host}:{actual_port}")
        click.echo(f"💡 Make sure the server is running with: devs-webhook serve --dev")
        
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")


def main():
    """Main CLI entry point."""
    cli()


if __name__ == '__main__':
    main()