"""CLI for webhook management."""

import os
import subprocess
import click
import httpx
import uvicorn
from httpx import BasicAuth
from pathlib import Path

from .config import get_config
from .utils.logging import setup_logging
from .cli.worker import worker


@click.group()
def cli():
    """DevContainer Webhook Handler CLI."""
    pass

# Add worker command to the CLI group
cli.add_command(worker)


@cli.command()
@click.option('--host', default=None, help='Host to bind to (webhook mode only)')
@click.option('--port', default=None, type=int, help='Port to bind to (webhook mode only)')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development (webhook mode only)')
@click.option('--env-file', type=click.Path(exists=True, path_type=Path), help='Path to .env file to load')
@click.option('--dev', is_flag=True, help='Development mode (auto-loads .env, enables reload, console logs)')
@click.option('--source', type=click.Choice(['webhook', 'sqs'], case_sensitive=False), help='Task source override')
@click.option('--burst', is_flag=True, help='Burst mode: process all available SQS messages then exit (SQS mode only)')
def serve(host: str, port: int, reload: bool, env_file: Path, dev: bool, source: str, burst: bool):
    """Start the webhook handler server.

    The server can run in two modes:
    - webhook: Receives GitHub webhooks via FastAPI HTTP endpoint (default)
    - sqs: Polls AWS SQS queue for webhook events

    SQS mode supports --burst flag to process all available messages then exit:
    - Exit code 0: Processed one or more messages successfully
    - Exit code 42: Queue was empty (no messages to process)
    - Other codes: Error occurred

    Examples:
        devs-webhook serve --dev                    # Development mode with .env loading
        devs-webhook serve --env-file /path/.env    # Load specific .env file
        devs-webhook serve --host 127.0.0.1        # Override host from config
        devs-webhook serve --source sqs            # Use SQS polling mode
        devs-webhook serve --source sqs --burst    # Process all SQS messages then exit
    """
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

    # Load .env file first (before creating config)
    if env_file:
        # Load the env file explicitly
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            click.echo("⚠️ python-dotenv not available, skipping .env file loading")

    # Set environment variables for dev mode
    if dev:
        os.environ["DEV_MODE"] = "true"
        os.environ["LOG_FORMAT"] = "console"
        if not source or source == "webhook":
            os.environ["WEBHOOK_HOST"] = "127.0.0.1"

    # Override task source if specified via CLI
    if source:
        os.environ["TASK_SOURCE"] = source

    # Now setup logging after environment is configured
    setup_logging()

    # Get config for display purposes (after loading env file)
    config = get_config()

    # Display configuration
    click.echo(f"Task source: {config.task_source}")
    click.echo(f"Watching for @{config.github_mentioned_user} mentions")
    click.echo(f"Container pool: {', '.join(config.get_container_pool_list())}")

    # Validate burst mode is only used with SQS
    if burst and config.task_source != "sqs":
        click.echo("❌ --burst flag is only valid with SQS mode (--source sqs)")
        exit(1)

    # Start the appropriate task source
    if config.task_source == "webhook":
        # Override config with CLI options
        actual_host = host or config.webhook_host
        actual_port = port or config.webhook_port

        click.echo(f"Starting webhook server on {actual_host}:{actual_port}")
        if dev:
            click.echo("🔧 Development mode enabled - /testevent endpoint available")

        uvicorn.run(
            "devs_webhook.app:app",
            host=actual_host,
            port=actual_port,
            reload=reload,
            log_config=None,  # Use our structlog config
        )

    elif config.task_source == "sqs":
        click.echo(f"Starting SQS polling from: {config.aws_sqs_queue_url}")
        click.echo(f"AWS region: {config.aws_region}")
        if config.aws_sqs_dlq_url:
            click.echo(f"DLQ configured: {config.aws_sqs_dlq_url}")
        if burst:
            click.echo("Burst mode: will process all messages then exit")

        # Import and run SQS source
        import asyncio
        from .sources.sqs_source import SQSTaskSource

        async def run_sqs():
            sqs_source = SQSTaskSource(burst_mode=burst)
            try:
                return await sqs_source.start()
            except KeyboardInterrupt:
                click.echo("\n🛑 Shutting down SQS polling...")
                await sqs_source.stop()
                return None

        try:
            result = asyncio.run(run_sqs())
            # Handle burst mode exit codes
            if burst and result is not None:
                if result.messages_processed == 0:
                    click.echo("Queue was empty, no messages processed")
                    exit(42)
                else:
                    click.echo(f"Burst complete: processed {result.messages_processed} message(s)")
                    exit(0)
        except KeyboardInterrupt:
            click.echo("🛑 Server stopped")

    else:
        click.echo(f"❌ Unknown task source: {config.task_source}")
        click.echo("   Valid options: webhook, sqs")
        exit(1)


@cli.command()
def status():
    """Show webhook handler status."""
    config = get_config()
    base_url = f"http://{config.webhook_host}:{config.webhook_port}"
    
    # Try authenticated /status endpoint first if credentials are available
    if config.admin_username and config.admin_password:
        try:
            auth = BasicAuth(config.admin_username, config.admin_password)
            response = httpx.get(f"{base_url}/status", auth=auth, timeout=5.0)
            
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
                return
                
        except Exception as e:
            # Fall through to health endpoint
            pass
    
    # Fall back to unauthenticated /health endpoint
    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            
            click.echo("🟢 Webhook Handler Health")
            click.echo(f"Service: {data['service']} v{data['version']}")
            click.echo(f"Status: {data['status']}")
            click.echo(f"Mentioned user: @{data['config']['mentioned_user']}")
            click.echo(f"Container pool: {data['config']['container_pool']}")
            click.echo(f"Dev mode: {data['dev_mode']}")
            
            click.echo("\n💡 For detailed status, configure admin credentials")
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
        click.echo(f"Workspace directory: {config.workspaces_dir}")
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
    config = get_config()
    url = f"http://{config.webhook_host}:{config.webhook_port}/container/{container_name}/stop"
    
    try:
        # Include authentication if available
        auth = None
        if config.admin_username and config.admin_password:
            auth = BasicAuth(config.admin_username, config.admin_password)
        
        response = httpx.post(url, auth=auth, timeout=10.0)
        if response.status_code == 200:
            click.echo(f"✅ Container {container_name} stopped")
        elif response.status_code == 404:
            click.echo(f"❌ Container {container_name} not found")
        elif response.status_code == 401:
            click.echo(f"❌ Authentication required. Configure admin credentials.")
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
        result = subprocess.run(['gh', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ GitHub CLI available")
        else:
            click.echo("❌ GitHub CLI not working")
    except FileNotFoundError:
        click.echo("❌ GitHub CLI not installed")
    
    # Test Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ Docker available")
        else:
            click.echo("❌ Docker not working")
    except FileNotFoundError:
        click.echo("❌ Docker not installed")
    
    # Test DevContainer CLI
    try:
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
        
        # Include authentication if available
        auth = None
        if config.admin_username and config.admin_password:
            auth = BasicAuth(config.admin_username, config.admin_password)
        
        response = httpx.post(
            url,
            json=payload,
            auth=auth,
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