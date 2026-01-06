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
@click.option('--no-wait', is_flag=True, help='In burst mode, exit immediately after draining SQS queue without waiting for tasks to complete')
@click.option('--timeout', type=int, default=None, help='Timeout in seconds for waiting on task completion in burst mode (default: wait indefinitely)')
@click.option('--container-logs', is_flag=True, help='Enable container output logging to files (CloudWatch compatible)')
@click.option('--container-logs-dir', type=click.Path(path_type=Path), default=None, help='Directory for container log files (default: ~/.devs/logs/webhook/containers)')
def serve(host: str, port: int, reload: bool, env_file: Path, dev: bool, source: str, burst: bool, no_wait: bool, timeout: int, container_logs: bool, container_logs_dir: Path):
    """Start the webhook handler server.

    The server can run in two modes:
    - webhook: Receives GitHub webhooks via FastAPI HTTP endpoint (default)
    - sqs: Polls AWS SQS queue for webhook events

    SQS mode supports --burst flag to process all available messages then exit:
    - Exit code 0: Processed one or more messages successfully
    - Exit code 42: Queue was empty (no messages to process)
    - Exit code 43: Timeout waiting for tasks to complete
    - Other codes: Error occurred

    By default, burst mode waits for all container tasks (Docker jobs) to complete
    before exiting. Use --no-wait to exit immediately after draining the SQS queue,
    or --timeout to set a maximum wait time.

    Examples:
        devs-webhook serve --dev                    # Development mode with .env loading
        devs-webhook serve --env-file /path/.env    # Load specific .env file
        devs-webhook serve --host 127.0.0.1        # Override host from config
        devs-webhook serve --source sqs            # Use SQS polling mode
        devs-webhook serve --source sqs --burst    # Process all SQS messages, wait for completion
        devs-webhook serve --source sqs --burst --no-wait  # Drain SQS and exit immediately
        devs-webhook serve --source sqs --burst --timeout 3600  # Wait up to 1 hour for tasks
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

    # Configure container logs if specified via CLI
    if container_logs:
        os.environ["CONTAINER_LOGS_ENABLED"] = "true"
    if container_logs_dir:
        os.environ["CONTAINER_LOGS_DIR"] = str(container_logs_dir)

    # Now setup logging after environment is configured
    setup_logging()

    # Get config for display purposes (after loading env file)
    config = get_config()

    # Display configuration
    click.echo(f"Task source: {config.task_source}")
    click.echo(f"Watching for @{config.github_mentioned_user} mentions")
    click.echo(f"Container pool: {', '.join(config.get_container_pool_list())}")
    if config.container_logs_enabled:
        click.echo(f"Container logs: {config.container_logs_dir}")

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
            if no_wait:
                click.echo("  --no-wait: will NOT wait for container tasks to complete")
            else:
                if timeout:
                    click.echo(f"  Will wait up to {timeout}s for container tasks to complete")
                else:
                    click.echo("  Will wait for all container tasks to complete before exit")

        # Import and run SQS source
        import asyncio
        from .sources.sqs_source import SQSTaskSource

        async def run_sqs():
            sqs_source = SQSTaskSource(
                burst_mode=burst,
                wait_for_tasks=not no_wait,
                task_timeout=float(timeout) if timeout else None,
            )
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
                elif no_wait:
                    # Not waiting for tasks - just report messages processed
                    click.echo(f"Burst complete: queued {result.messages_processed} message(s)")
                    click.echo("  (not waiting for container tasks to complete)")
                    exit(0)
                elif result.tasks_completed == result.messages_processed:
                    # All tasks completed successfully
                    click.echo(f"Burst complete: processed {result.messages_processed} message(s), "
                              f"all {result.tasks_completed} task(s) completed")
                    exit(0)
                elif result.tasks_completed < result.messages_processed:
                    # Timeout - some tasks didn't complete
                    remaining = result.messages_processed - result.tasks_completed
                    click.echo(f"Burst timeout: processed {result.messages_processed} message(s), "
                              f"but {remaining} task(s) still running")
                    exit(43)
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
@click.option('--host', default='127.0.0.1', help='Webhook server host (default: 127.0.0.1)')
@click.option('--port', default=8000, type=int, help='Webhook server port (default: 8000)')
@click.option('--username', default=None, help='Admin username for authentication')
@click.option('--password', default=None, help='Admin password for authentication')
def test(prompt: str, repo: str, host: str, port: int, username: str, password: str):
    """Send a test prompt to the webhook handler.

    This sends a test event to the /testevent endpoint, which is only available
    in development mode.

    Examples:
        devs-webhook test "Fix the login bug"
        devs-webhook test "Add dark mode toggle" --repo myorg/myproject
    """
    # Use CLI options or environment variables
    actual_host = host or os.environ.get('WEBHOOK_HOST', '127.0.0.1')
    actual_port = port or int(os.environ.get('WEBHOOK_PORT', '8000'))
    admin_username = username or os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = password or os.environ.get('ADMIN_PASSWORD', '')
    url = f"http://{actual_host}:{actual_port}/testevent"

    payload = {
        "prompt": prompt,
        "repo": repo
    }

    try:
        click.echo(f"🧪 Sending test event to {url}")
        click.echo(f"📝 Prompt: {prompt}")
        click.echo(f"📦 Repository: {repo}")

        # Always include authentication (server requires it, even in dev mode)
        auth = BasicAuth(admin_username, admin_password)

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


@cli.command()
@click.option('--all', 'cleanup_all', is_flag=True, help='Clean up all managed containers (not just idle ones)')
@click.option('--max-age-hours', default=None, type=int, help='Override max age threshold (default: from config or 10)')
@click.option('--idle-minutes', default=None, type=int, help='Override idle timeout (default: from config or 60)')
@click.option('--dry-run', is_flag=True, help='Show what would be cleaned up without actually doing it')
def cleanup(cleanup_all: bool, max_age_hours: int, idle_minutes: int, dry_run: bool):
    """Clean up idle and old containers.

    This command finds containers managed by devs-webhook and cleans up those that
    are idle (exited, or running but not processing) and either:
    - Idle for longer than the idle timeout
    - Older than the max age threshold

    Use this after burst mode processing completes, or via cron for periodic cleanup.

    Examples:
        devs-webhook cleanup                    # Clean up idle containers exceeding thresholds
        devs-webhook cleanup --all              # Clean up ALL managed containers
        devs-webhook cleanup --dry-run          # Show what would be cleaned up
        devs-webhook cleanup --max-age-hours 2  # Override max age to 2 hours
    """
    from datetime import datetime, timezone, timedelta
    from devs_common.utils.docker_client import DockerClient
    from devs_common.core.workspace import WorkspaceManager
    from devs_common.core.project import Project

    try:
        config = get_config()
    except Exception:
        # Config validation may fail without all env vars - use defaults
        config = None

    # Use config values or defaults
    max_age = timedelta(hours=max_age_hours or (config.container_max_age_hours if config else 10))
    idle_timeout = timedelta(minutes=idle_minutes or (config.container_timeout_minutes if config else 60))

    click.echo("🧹 Container Cleanup")
    click.echo(f"   Max age: {max_age.total_seconds() / 3600:.1f} hours")
    click.echo(f"   Idle timeout: {idle_timeout.total_seconds() / 60:.0f} minutes")
    if cleanup_all:
        click.echo("   Mode: Clean ALL managed containers")
    if dry_run:
        click.echo("   Mode: DRY RUN (no changes will be made)")
    click.echo()

    try:
        docker = DockerClient()
    except Exception as e:
        click.echo(f"❌ Failed to connect to Docker: {e}")
        return

    # Find all devs-managed containers
    try:
        containers = docker.find_containers_by_labels({"devs.managed": "true"})
    except Exception as e:
        click.echo(f"❌ Failed to list containers: {e}")
        return

    if not containers:
        click.echo("✅ No managed containers found")
        return

    click.echo(f"Found {len(containers)} managed container(s)")

    now = datetime.now(tz=timezone.utc)
    cleaned = 0
    skipped = 0

    for container_data in containers:
        container_name = container_data['name']
        status = container_data['status']
        created_str = container_data['created']
        labels = container_data['labels']

        # Parse creation time
        try:
            # Docker timestamp format: 2024-01-15T10:30:00.123456789Z
            created = datetime.fromisoformat(created_str.replace('Z', '+00:00').split('.')[0] + '+00:00')
        except Exception:
            created = now  # Assume recent if can't parse

        age = now - created
        dev_name = labels.get('devs.dev', 'unknown')
        project_name = labels.get('devs.project', 'unknown')

        # Determine if we should clean up this container
        should_cleanup = False
        reason = ""

        if cleanup_all:
            should_cleanup = True
            reason = "cleanup all requested"
        elif status in ['exited', 'dead', 'created']:
            # Container is not running - safe to clean up if old enough
            if age > idle_timeout:
                should_cleanup = True
                reason = f"exited and idle {age.total_seconds() / 60:.0f}min"
        elif status == 'running':
            # Running container - only clean up if exceeds max age
            # (We can't easily tell if it's truly idle without more context)
            if age > max_age:
                should_cleanup = True
                reason = f"running but age {age.total_seconds() / 3600:.1f}h exceeds max"

        if should_cleanup:
            age_str = f"{age.total_seconds() / 3600:.1f}h" if age.total_seconds() > 3600 else f"{age.total_seconds() / 60:.0f}m"
            click.echo(f"  🗑️  {container_name} ({status}, age {age_str}) - {reason}")

            if not dry_run:
                try:
                    # Stop and remove the container
                    container = docker.client.containers.get(container_data['id'])
                    if status == 'running':
                        container.stop(timeout=10)
                    container.remove(force=True)

                    # Also try to remove the workspace
                    workspaces_dir = Path.home() / ".devs" / "workspaces"
                    workspace_pattern = f"{project_name}-{dev_name}"
                    for workspace in workspaces_dir.glob(f"{workspace_pattern}*"):
                        if workspace.is_dir():
                            import shutil
                            shutil.rmtree(workspace)
                            click.echo(f"      Removed workspace: {workspace.name}")

                    cleaned += 1
                except Exception as e:
                    click.echo(f"      ❌ Failed to clean up: {e}")
        else:
            skipped += 1

    click.echo()
    if dry_run:
        click.echo(f"🔍 Dry run complete: {len(containers) - skipped} would be cleaned, {skipped} would be kept")
    else:
        click.echo(f"✅ Cleanup complete: {cleaned} cleaned, {skipped} kept")


@cli.command('test-runtests')
@click.option('--repo', required=True, help='Repository name (org/repo format)')
@click.option('--branch', default='main', help='Branch to test (default: main)')
@click.option('--commit', default='HEAD', help='Commit SHA to test (default: HEAD)')
@click.option('--pr', default=None, type=int, help='PR number (creates PR event instead of push event)')
@click.option('--host', default='127.0.0.1', help='Webhook server host (default: 127.0.0.1)')
@click.option('--port', default=8000, type=int, help='Webhook server port (default: 8000)')
@click.option('--username', default=None, help='Admin username for authentication')
@click.option('--password', default=None, help='Admin password for authentication')
def test_runtests(repo: str, branch: str, commit: str, pr: int, host: str, port: int, username: str, password: str):
    """Send a test CI/runtests event to the webhook handler.

    This sends a test push or PR event to the /testruntests endpoint, which is only
    available in development mode. GitHub Checks API calls are skipped.

    Examples:
        devs-webhook test-runtests --repo myorg/myproject
        devs-webhook test-runtests --repo myorg/myproject --branch feature-branch
        devs-webhook test-runtests --repo myorg/myproject --commit abc123
        devs-webhook test-runtests --repo myorg/myproject --pr 42 --branch feature --commit abc123
    """
    # Use CLI options or environment variables
    actual_host = host or os.environ.get('WEBHOOK_HOST', '127.0.0.1')
    actual_port = port or int(os.environ.get('WEBHOOK_PORT', '8000'))
    admin_username = username or os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = password or os.environ.get('ADMIN_PASSWORD', '')
    url = f"http://{actual_host}:{actual_port}/testruntests"

    payload = {
        "repo": repo,
        "branch": branch,
        "commit_sha": commit
    }
    if pr is not None:
        payload["pr_number"] = pr

    event_type = "PR" if pr else "push"
    try:
        click.echo(f"🧪 Sending test CI event ({event_type}) to {url}")
        click.echo(f"📦 Repository: {repo}")
        click.echo(f"🌿 Branch: {branch}")
        click.echo(f"📝 Commit: {commit}")
        if pr:
            click.echo(f"🔀 PR: #{pr}")

        # Always include authentication (server requires it, even in dev mode)
        auth = BasicAuth(admin_username, admin_password)

        response = httpx.post(
            url,
            json=payload,
            auth=auth,
            timeout=10.0
        )

        if response.status_code == 202:
            data = response.json()
            click.echo(f"\n✅ Test CI event accepted!")
            click.echo(f"🆔 Delivery ID: {data['delivery_id']}")
            click.echo(f"📋 Status: {data['status']}")
            click.echo(f"\n💡 GitHub Checks API calls will be skipped")
            click.echo(f"💡 Check logs or /status endpoint for processing updates")

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