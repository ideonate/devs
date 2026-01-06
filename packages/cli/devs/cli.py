"""Command-line interface for devs package."""

import os
import sys
import subprocess
from functools import wraps

import click
from rich.console import Console
from rich.table import Table

from .config import config
from pathlib import Path
from .core import Project, ContainerManager, WorkspaceManager
from .core.integration import VSCodeIntegration, ExternalToolIntegration
from devs_common.devs_config import DevsConfigLoader
from .exceptions import (
    DevsError,
    ProjectNotFoundError,
    DevcontainerConfigError,
    ContainerError,
    WorkspaceError,
    VSCodeError,
    DependencyError
)

console = Console()


def parse_env_vars(env_tuples: tuple) -> dict:
    """Parse environment variables from --env options.
    
    Args:
        env_tuples: Tuple of strings in format 'VAR=value'
        
    Returns:
        Dictionary of environment variables
        
    Raises:
        click.BadParameter: If format is invalid
    """
    env_dict = {}
    for env_str in env_tuples:
        if '=' not in env_str:
            raise click.BadParameter(f"Environment variable must be in format VAR=value, got: {env_str}")
        key, value = env_str.split('=', 1)
        env_dict[key] = value
    return env_dict


def merge_env_vars(devs_env: dict, cli_env: dict) -> dict:
    """Merge environment variables with CLI taking priority over DEVS.yml.
    
    Args:
        devs_env: Environment variables from DEVS.yml
        cli_env: Environment variables from CLI --env flags
        
    Returns:
        Merged environment variables with CLI overrides applied
    """
    if not devs_env and not cli_env:
        return {}
    
    # Start with DEVS.yml env vars
    merged = devs_env.copy() if devs_env else {}
    
    # CLI env vars take priority
    if cli_env:
        merged.update(cli_env)
    
    return merged


def debug_option(f):
    """Decorator to add debug option and handle debug flag inheritance."""
    @click.option('--debug', is_flag=True, help='Show debug tracebacks on error')
    @click.pass_context
    @wraps(f)
    def wrapper(ctx, *args, debug=False, **kwargs):
        # Use command-level debug flag if provided, otherwise fall back to group-level
        debug = debug or ctx.obj.get('DEBUG', False)
        ctx.obj['DEBUG'] = debug  # Update context for consistency
        return f(*args, debug=debug, **kwargs)
    return wrapper


def check_dependencies() -> None:
    """Check and report on dependencies."""
    integration = ExternalToolIntegration(Project())
    missing = integration.get_missing_dependencies()
    
    if missing:
        console.print(f"❌ Missing dependencies: {', '.join(missing)}")
        console.print("\nInstall missing tools:")
        for tool in missing:
            if tool == 'devcontainer':
                console.print("   npm install -g @devcontainers/cli")
            elif tool == 'docker':
                console.print("   Install Docker Desktop or Docker Engine")
            elif tool == 'code':
                console.print("   Install VS Code and ensure 'code' command is in PATH")
        sys.exit(1)


def get_project() -> Project:
    """Get project instance with error handling."""
    try:
        project = Project()
        # No longer require devcontainer config upfront - 
        # WorkspaceManager will provide default template if needed
        return project
    except ProjectNotFoundError as e:
        console.print(f"❌ {e}")
        sys.exit(1)


@click.group()
@click.version_option(version="0.1.0", prog_name="devs")
@click.option('--debug', is_flag=True, help='Show debug tracebacks on error')
@click.pass_context
def cli(ctx, debug: bool) -> None:
    """DevContainer Management Tool
    
    Manage multiple named devcontainers for any project.
    """
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug


@cli.command()
@click.argument('dev_names', nargs=-1, required=True)
@click.option('--rebuild', is_flag=True, help='Force rebuild of container images')
@click.option('--live', is_flag=True, help='Mount current directory as workspace instead of copying')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def start(dev_names: tuple, rebuild: bool, live: bool, env: tuple, debug: bool) -> None:
    """Start named devcontainers.
    
    DEV_NAMES: One or more development environment names to start
    
    Example: devs start sally bob
    Example: devs start sally --live  # Mount current directory directly
    Example: devs start sally --env QUART_PORT=5001 --env DB_HOST=localhost:3307
    """
    check_dependencies()
    project = get_project()
    
    console.print(f"🚀 Starting devcontainers for project: {project.info.name}")
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    for dev_name in dev_names:
        console.print(f"   Starting: {dev_name}")
        
        # Load environment variables from DEVS.yml and merge with CLI --env flags
        devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
        cli_env = parse_env_vars(env) if env else {}
        extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None
        
        if extra_env:
            console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")
        
        try:
            # Create/ensure workspace exists (handles live mode internally)
            workspace_dir = workspace_manager.create_workspace(dev_name, live=live)
            
            # Ensure container is running
            if container_manager.ensure_container_running(
                dev_name, 
                workspace_dir, 
                force_rebuild=rebuild,
                debug=debug,
                live=live,
                extra_env=extra_env
            ):
                continue
            else:
                console.print(f"   ⚠️  Failed to start {dev_name}, continuing with others...")
                
        except (ContainerError, WorkspaceError) as e:
            console.print(f"   ❌ Error starting {dev_name}: {e}")
            continue
    
    console.print("")
    console.print("💡 To open containers in VS Code:")
    console.print(f"   devs vscode {' '.join(dev_names)}")
    console.print("")
    console.print("💡 To open containers in shell:")
    console.print(f"   devs shell {dev_names[0] if dev_names else '<dev-name>'}")


@cli.command()
@click.argument('dev_names', nargs=-1, required=True)
@click.option('--delay', default=2.0, help='Delay between opening VS Code windows (seconds)')
@click.option('--live', is_flag=True, help='Start containers with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def vscode(dev_names: tuple, delay: float, live: bool, env: tuple, debug: bool) -> None:
    """Open devcontainers in VS Code.
    
    DEV_NAMES: One or more development environment names to open
    
    Example: devs vscode sally bob
    Example: devs vscode sally --live  # Start with current directory mounted
    Example: devs vscode sally --env QUART_PORT=5001
    """
    check_dependencies()
    project = get_project()
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    vscode = VSCodeIntegration(project)
    
    workspace_dirs = []
    valid_dev_names = []
    
    for dev_name in dev_names:
        console.print(f"   Preparing: {dev_name}")
        
        # Load environment variables from DEVS.yml and merge with CLI --env flags
        devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
        cli_env = parse_env_vars(env) if env else {}
        extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None
        
        if extra_env:
            console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")
        
        try:
            # Ensure workspace exists (handles live mode internally)
            workspace_dir = workspace_manager.create_workspace(dev_name, live=live)
            
            # Ensure container is running before launching VS Code
            if container_manager.ensure_container_running(dev_name, workspace_dir, debug=debug, live=live, extra_env=extra_env):
                workspace_dirs.append(workspace_dir)
                valid_dev_names.append(dev_name)
            else:
                console.print(f"   ❌ Failed to start container for {dev_name}, skipping...")
                
        except (ContainerError, WorkspaceError) as e:
            console.print(f"   ❌ Error preparing {dev_name}: {e}")
            continue
    
    if workspace_dirs:
        try:
            success_count = vscode.launch_multiple_devcontainers(
                workspace_dirs, 
                valid_dev_names,
                delay_between_windows=delay,
                live=live
            )
            
            if success_count == 0:
                console.print("❌ Failed to open any VS Code windows")
                
        except VSCodeError as e:
            console.print(f"❌ VS Code integration error: {e}")


@cli.command()
@click.argument('dev_names', nargs=-1, required=True) 
def stop(dev_names: tuple) -> None:
    """Stop and remove devcontainers.
    
    DEV_NAMES: One or more development environment names to stop
    
    Example: devs stop sally
    """
    check_dependencies()
    project = get_project()
    
    console.print(f"🛑 Stopping devcontainers for project: {project.info.name}")
    
    container_manager = ContainerManager(project, config)
    
    for dev_name in dev_names:
        console.print(f"   Stopping: {dev_name}")
        container_manager.stop_container(dev_name)


@cli.command()
@click.argument('dev_name')
@click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def shell(dev_name: str, live: bool, env: tuple, debug: bool) -> None:
    """Open shell in devcontainer.
    
    DEV_NAME: Development environment name
    
    Example: devs shell sally
    Example: devs shell sally --live  # Start with current directory mounted
    Example: devs shell sally --env QUART_PORT=5001
    """
    check_dependencies()
    project = get_project()
    
    # Load environment variables from DEVS.yml and merge with CLI --env flags
    devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
    cli_env = parse_env_vars(env) if env else {}
    extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None
    
    if extra_env:
        console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    try:
        # Ensure workspace exists (handles live mode internally)
        workspace_dir = workspace_manager.create_workspace(dev_name, live=live)
        # Ensure container is running
        container_manager.ensure_container_running(
            dev_name=dev_name, 
            workspace_dir=workspace_dir, 
            force_rebuild=False, 
            debug=debug, 
            live=live, 
            extra_env=extra_env
        )
        
        # Open shell
        container_manager.exec_shell(dev_name, workspace_dir, debug=debug, live=live)
        
    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error opening shell for {dev_name}: {e}")
        sys.exit(1)


@cli.command()
@click.argument('dev_name', required=False)
@click.argument('prompt', required=False)
@click.option('--auth', is_flag=True, help='Set up Claude authentication for devcontainers')
@click.option('--api-key', help='Claude API key to authenticate with (use with --auth)')
@click.option('--reset-workspace', is_flag=True, help='Reset workspace contents before execution')
@click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def claude(dev_name: str, prompt: str, auth: bool, api_key: str, reset_workspace: bool, live: bool, env: tuple, debug: bool) -> None:
    """Execute Claude CLI in devcontainer or set up authentication.

    DEV_NAME: Development environment name
    PROMPT: Prompt to send to Claude

    Example: devs claude sally "Summarize this codebase"
    Example: devs claude sally "Fix the tests" --reset-workspace
    Example: devs claude sally "Fix the tests" --live  # Run with current directory
    Example: devs claude sally "Start the server" --env QUART_PORT=5001
    Example: devs claude --auth                        # Interactive authentication
    Example: devs claude --auth --api-key <YOUR_KEY>   # API key authentication
    """
    # Handle authentication mode
    if auth:
        _handle_claude_auth(api_key=api_key, debug=debug)
        return

    # Validate required arguments for execution mode
    if not dev_name or not prompt:
        raise click.UsageError("DEV_NAME and PROMPT are required unless using --auth")

    check_dependencies()
    project = get_project()

    # Load environment variables from DEVS.yml and merge with CLI --env flags
    devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
    cli_env = parse_env_vars(env) if env else {}
    extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None

    if extra_env:
        console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")

    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)

    try:
        # Ensure workspace exists (handles live mode and reset internally)
        workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=reset_workspace, live=live)
        # Ensure container is running
        container_manager.ensure_container_running(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            force_rebuild=False,
            debug=debug,
            live=live,
            extra_env=extra_env
        )

        # Execute Claude
        console.print(f"🤖 Executing Claude in {dev_name}...")
        if reset_workspace and not live:
            console.print("🗑️  Workspace contents reset")
        console.print(f"📝 Prompt: {prompt}")
        console.print("")

        success, output, error, _ = container_manager.exec_claude(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            prompt=prompt,
            debug=debug,
            stream=True,
            live=live,
            extra_env=extra_env
        )

        console.print("")  # Add spacing after streamed output
        if success:
            console.print("✅ Claude execution completed")
        else:
            console.print("❌ Claude execution failed")
            if error:
                console.print("")
                console.print("🚫 Error:")
                console.print(error)
            sys.exit(1)

    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error executing Claude in {dev_name}: {e}")
        sys.exit(1)


def _handle_claude_auth(api_key: str, debug: bool) -> None:
    """Handle Claude authentication setup.

    This configures Claude authentication that will be shared across
    all devcontainers for this project. The authentication is stored
    on the host and bind-mounted into containers.
    """
    try:
        # Ensure Claude config directory exists
        config.ensure_directories()

        console.print("🔐 Setting up Claude authentication...")
        console.print(f"   Configuration will be saved to: {config.claude_config_dir}")

        if api_key:
            # Set API key directly using Claude CLI
            console.print("   Using provided API key...")

            # Set CLAUDE_CONFIG_DIR to our config directory and run auth with API key
            env = os.environ.copy()
            env['CLAUDE_CONFIG_DIR'] = str(config.claude_config_dir)

            cmd = ['claude', 'auth', '--key', api_key]

            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
                console.print(f"[dim]CLAUDE_CONFIG_DIR: {config.claude_config_dir}[/dim]")

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise Exception(f"Claude authentication failed: {error_msg}")

        else:
            # Interactive authentication
            console.print("   Starting interactive authentication...")
            console.print("   Follow the prompts to authenticate with Claude")
            console.print("")

            # Set CLAUDE_CONFIG_DIR to our config directory
            env = os.environ.copy()
            env['CLAUDE_CONFIG_DIR'] = str(config.claude_config_dir)

            cmd = ['claude', 'auth']

            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
                console.print(f"[dim]CLAUDE_CONFIG_DIR: {config.claude_config_dir}[/dim]")

            # Run interactively
            result = subprocess.run(
                cmd,
                env=env,
                check=False
            )

            if result.returncode != 0:
                raise Exception("Claude authentication was cancelled or failed")

        console.print("")
        console.print("✅ Claude authentication configured successfully!")
        console.print(f"   Configuration saved to: {config.claude_config_dir}")
        console.print("   This authentication will be shared across all devcontainers")
        console.print("")
        console.print("💡 You can now use Claude in any devcontainer:")
        console.print("   devs claude <dev-name> 'Your prompt here'")

    except FileNotFoundError:
        console.print("❌ Claude CLI not found on host machine")
        console.print("")
        console.print("Please install Claude CLI first:")
        console.print("   npm install -g @anthropic-ai/claude-cli")
        console.print("")
        console.print("Note: Claude needs to be installed on the host machine")
        console.print("      for authentication. It's already available in containers.")
        sys.exit(1)

    except Exception as e:
        console.print(f"❌ Failed to configure Claude authentication: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.argument('dev_name', required=False)
@click.argument('prompt', required=False)
@click.option('--auth', is_flag=True, help='Set up Codex authentication for devcontainers')
@click.option('--api-key', help='OpenAI API key to authenticate with (use with --auth)')
@click.option('--reset-workspace', is_flag=True, help='Reset workspace contents before execution')
@click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def codex(dev_name: str, prompt: str, auth: bool, api_key: str, reset_workspace: bool, live: bool, env: tuple, debug: bool) -> None:
    """Execute OpenAI Codex CLI in devcontainer or set up authentication.

    DEV_NAME: Development environment name
    PROMPT: Prompt to send to Codex

    Example: devs codex sally "Summarize this codebase"
    Example: devs codex sally "Fix the tests" --reset-workspace
    Example: devs codex sally "Fix the tests" --live  # Run with current directory
    Example: devs codex sally "Start the server" --env QUART_PORT=5001
    Example: devs codex --auth                        # Interactive authentication
    Example: devs codex --auth --api-key <YOUR_KEY>   # API key authentication
    """
    # Handle authentication mode
    if auth:
        _handle_codex_auth(api_key=api_key, debug=debug)
        return

    # Validate required arguments for execution mode
    if not dev_name or not prompt:
        raise click.UsageError("DEV_NAME and PROMPT are required unless using --auth")

    check_dependencies()
    project = get_project()

    # Load environment variables from DEVS.yml and merge with CLI --env flags
    devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
    cli_env = parse_env_vars(env) if env else {}
    extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None

    if extra_env:
        console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")

    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)

    try:
        # Ensure workspace exists (handles live mode and reset internally)
        workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=reset_workspace, live=live)
        # Ensure container is running
        container_manager.ensure_container_running(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            force_rebuild=False,
            debug=debug,
            live=live,
            extra_env=extra_env
        )

        # Execute Codex
        console.print(f"🤖 Executing Codex in {dev_name}...")
        if reset_workspace and not live:
            console.print("🗑️  Workspace contents reset")
        console.print(f"📝 Prompt: {prompt}")
        console.print("")

        success, output, error, _ = container_manager.exec_codex(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            prompt=prompt,
            debug=debug,
            stream=True,
            live=live,
            extra_env=extra_env
        )

        console.print("")  # Add spacing after streamed output
        if success:
            console.print("✅ Codex execution completed")
        else:
            console.print("❌ Codex execution failed")
            if error:
                console.print("")
                console.print("🚫 Error:")
                console.print(error)
            sys.exit(1)

    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error executing Codex in {dev_name}: {e}")
        sys.exit(1)


def _handle_codex_auth(api_key: str, debug: bool) -> None:
    """Handle Codex authentication setup.

    This configures Codex authentication that will be shared across
    all devcontainers for this project. The authentication is stored
    on the host and bind-mounted into containers.
    """
    try:
        # Ensure Codex config directory exists
        config.ensure_directories()

        console.print("🔐 Setting up Codex authentication...")
        console.print(f"   Configuration will be saved to: {config.codex_config_dir}")

        if api_key:
            # Set API key directly using Codex CLI
            console.print("   Using provided API key...")

            # Set CODEX_CONFIG_HOME to our config directory and run auth with API key
            env = os.environ.copy()
            env['CODEX_CONFIG_HOME'] = str(config.codex_config_dir)

            cmd = ['codex', 'auth', '--api-key', api_key]

            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
                console.print(f"[dim]CODEX_CONFIG_HOME: {config.codex_config_dir}[/dim]")

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise Exception(f"Codex authentication failed: {error_msg}")

        else:
            # Interactive authentication
            console.print("   Starting interactive authentication...")
            console.print("   Follow the prompts to authenticate with Codex")
            console.print("")

            # Set CODEX_CONFIG_HOME to our config directory
            env = os.environ.copy()
            env['CODEX_CONFIG_HOME'] = str(config.codex_config_dir)

            cmd = ['codex', 'auth']

            if debug:
                console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
                console.print(f"[dim]CODEX_CONFIG_HOME: {config.codex_config_dir}[/dim]")

            # Run interactively
            result = subprocess.run(
                cmd,
                env=env,
                check=False
            )

            if result.returncode != 0:
                raise Exception("Codex authentication was cancelled or failed")

        console.print("")
        console.print("✅ Codex authentication configured successfully!")
        console.print(f"   Configuration saved to: {config.codex_config_dir}")
        console.print("   This authentication will be shared across all devcontainers")
        console.print("")
        console.print("💡 You can now use Codex in any devcontainer:")
        console.print("   devs codex <dev-name> 'Your prompt here'")

    except FileNotFoundError:
        console.print("❌ Codex CLI not found on host machine")
        console.print("")
        console.print("Please install Codex CLI first:")
        console.print("   npm install -g @openai/codex")
        console.print("")
        console.print("Note: Codex needs to be installed on the host machine")
        console.print("      for authentication. It's already available in containers.")
        sys.exit(1)

    except Exception as e:
        console.print(f"❌ Failed to configure Codex authentication: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.argument('dev_name')
@click.option('--reset-workspace', is_flag=True, help='Reset workspace contents before execution')
@click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def runtests(dev_name: str, reset_workspace: bool, live: bool, env: tuple, debug: bool) -> None:
    """Run tests in devcontainer.
    
    DEV_NAME: Development environment name
    
    Example: devs runtests sally
    Example: devs runtests sally --reset-workspace
    Example: devs runtests sally --live  # Run with current directory
    Example: devs runtests sally --env NODE_ENV=test
    """
    check_dependencies()
    project = get_project()
    
    # Load full DEVS configuration
    try:
        project_name = project.info.name
    except Exception:
        project_name = None
    
    devs_config = DevsConfigLoader.load(project_name)
    
    # Get test command from config
    command = devs_config.ci_test_command
    
    # Load environment variables from DEVS.yml and merge with CLI --env flags
    devs_env = devs_config.get_env_vars(dev_name)
    cli_env = parse_env_vars(env) if env else {}
    extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None
    
    if extra_env:
        console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    try:
        # Ensure workspace exists (handles live mode and reset internally)
        workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=reset_workspace, live=live)
        # Ensure container is running
        container_manager.ensure_container_running(
            dev_name=dev_name, 
            workspace_dir=workspace_dir, 
            force_rebuild=False, 
            debug=debug, 
            live=live, 
            extra_env=extra_env
        )
        
        # Execute test command
        console.print(f"🧪 Running tests in {dev_name}...")
        if reset_workspace and not live:
            console.print("🗑️  Workspace contents reset")
        console.print(f"🔧 Command: {command}")
        console.print("")
        
        success, output, error, _ = container_manager.exec_command(
            dev_name=dev_name,
            workspace_dir=workspace_dir,
            command=command,
            debug=debug,
            stream=True,
            live=live,
            extra_env=extra_env
        )
        
        console.print("")  # Add spacing after streamed output
        if success:
            console.print("✅ Tests completed successfully")
        else:
            console.print("❌ Tests failed")
            if error:
                console.print("")
                console.print("🚫 Error:")
                console.print(error)
            sys.exit(1)
        
    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error running tests in {dev_name}: {e}")
        sys.exit(1)


@cli.command()
@click.option('--all-projects', is_flag=True, help='List containers for all projects')
def list(all_projects: bool) -> None:
    """List active devcontainers for current project."""
    check_dependencies() 
    
    if all_projects:
        console.print("📋 All devcontainers:")
        # This would require a more complex implementation
        console.print("   --all-projects not implemented yet")
        return
    
    project = get_project()
    container_manager = ContainerManager(project, config)
    
    console.print(f"📋 Active devcontainers for project: {project.info.name}")
    console.print("")
    
    try:
        containers = container_manager.list_containers()
        
        if not containers:
            console.print("   No active devcontainers found")
            console.print("")
            console.print("💡 Start some with: devs start <dev-name>")
            return
        
        # Create a table
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Mode", style="yellow")
        table.add_column("Status", style="green")
        table.add_column("Container", style="dim")
        table.add_column("Created", style="dim")
        
        for container in containers:
            created_str = container.created.strftime("%Y-%m-%d %H:%M") if container.created else "unknown"
            mode = "live" if container.labels.get('devs.live') == 'true' else "copy"
            table.add_row(
                container.dev_name,
                mode,
                container.status,
                container.name,
                created_str
            )
        
        console.print(table)
        console.print("")
        console.print("💡 Open with: devs vscode <dev-name>")
        console.print("💡 Shell into: devs shell <dev-name>")
        console.print("💡 Stop with: devs stop <dev-name>")
        
    except ContainerError as e:
        console.print(f"❌ Error listing containers: {e}")


@cli.command()
def status() -> None:
    """Show project and dependency status."""
    try:
        project = Project()
        
        console.print(f"📁 Project: {project.info.name}")
        console.print(f"   Directory: {project.info.directory}")
        console.print(f"   Git repo: {'Yes' if project.info.is_git_repo else 'No'}")
        if project.info.git_remote_url:
            console.print(f"   Remote URL: {project.info.git_remote_url}")
        
        # Check devcontainer config
        try:
            project.check_devcontainer_config()
            console.print("   DevContainer config: ✅ Found in project")
        except DevcontainerConfigError:
            console.print("   DevContainer config: 📋 Will use default template")
        
        # Show dependency status
        integration = ExternalToolIntegration(project)
        integration.print_dependency_status()
        
        # Show workspace info
        workspace_manager = WorkspaceManager(project, config)
        workspaces = workspace_manager.list_workspaces()
        if workspaces:
            console.print(f"\n📂 Workspaces ({len(workspaces)}):")
            for workspace in workspaces:
                console.print(f"   - {workspace}")
        
    except ProjectNotFoundError as e:
        console.print(f"❌ {e}")


@cli.command()
@click.argument('dev_names', nargs=-1)
@click.option('--aborted', is_flag=True, help='Only clean up aborted/failed containers (skip workspaces)')
@click.option('--exclude-aborted', is_flag=True, help='Skip cleaning aborted containers (only clean workspaces)')
@click.option('--all-projects', is_flag=True, help='Clean aborted containers and unused workspaces from all projects')
def clean(dev_names: tuple, aborted: bool, exclude_aborted: bool, all_projects: bool) -> None:
    """Clean up workspaces and containers.
    
    By default, cleans up aborted containers first, then unused workspaces.
    
    DEV_NAMES: Specific development environments to clean up
    """
    check_dependencies()
    project = get_project()
    
    workspace_manager = WorkspaceManager(project, config)
    container_manager = ContainerManager(project, config)
    
    if aborted:
        # Clean up aborted/failed containers only
        try:
            console.print("🔍 Looking for aborted containers...")
            aborted_containers = container_manager.find_aborted_containers(all_projects=all_projects)
            
            if not aborted_containers:
                scope = "all projects" if all_projects else f"project: {project.info.name}"
                console.print(f"✅ No aborted containers found for {scope}")
                return
            
            console.print(f"Found {len(aborted_containers)} aborted container(s):")
            for container in aborted_containers:
                console.print(f"   - {container.name} ({container.project_name}/{container.dev_name}) - Status: {container.status}")
            
            console.print("")
            removed_count = container_manager.remove_aborted_containers(aborted_containers)
            console.print(f"🗑️  Removed {removed_count} aborted container(s)")
            
        except ContainerError as e:
            console.print(f"❌ Error cleaning aborted containers: {e}")
    
    elif dev_names:
        # Clean specific dev environments (both containers and workspaces)
        for dev_name in dev_names:
            console.print(f"🗑️  Cleaning up {dev_name}...")
            # Stop and remove container if it exists
            container_manager.stop_container(dev_name)
            # Remove workspace
            workspace_manager.remove_workspace(dev_name)
    
    else:
        # Default behavior: clean aborted containers first, then unused workspaces
        aborted_count = 0
        workspace_count = 0
        
        # Step 1: Clean aborted containers (unless excluded)
        if not exclude_aborted:
            try:
                console.print("🔍 Looking for aborted containers...")
                aborted_containers = container_manager.find_aborted_containers(all_projects=all_projects)
                
                if aborted_containers:
                    console.print(f"Found {len(aborted_containers)} aborted container(s):")
                    for container in aborted_containers:
                        console.print(f"   - {container.name} ({container.project_name}/{container.dev_name}) - Status: {container.status}")
                    
                    console.print("")
                    aborted_count = container_manager.remove_aborted_containers(aborted_containers)
                    console.print(f"🗑️  Removed {aborted_count} aborted container(s)")
                else:
                    console.print("✅ No aborted containers found")
                
                if aborted_containers:
                    console.print("")  # Add spacing between steps
                    
            except ContainerError as e:
                console.print(f"❌ Error cleaning aborted containers: {e}")
                console.print("")
        
        # Step 2: Clean unused workspaces
        try:
            if all_projects:
                console.print("🔍 Looking for unused workspaces across all projects...")
                workspace_count = workspace_manager.cleanup_unused_workspaces_all_projects(container_manager.docker)
            else:
                console.print("🔍 Looking for unused workspaces...")
                containers = container_manager.list_containers()
                active_dev_names = {c.dev_name for c in containers if c.status == 'running'}
                workspace_count = workspace_manager.cleanup_unused_workspaces(active_dev_names)
            
            if workspace_count > 0:
                scope = "across all projects" if all_projects else f"for project: {project.info.name}"
                console.print(f"🗑️  Cleaned up {workspace_count} unused workspace(s) {scope}")
            else:
                scope = "across all projects" if all_projects else f"for project: {project.info.name}"
                console.print(f"✅ No unused workspaces found {scope}")
                
        except ContainerError as e:
            console.print(f"❌ Error during workspace cleanup: {e}")
        
        # Summary
        if not exclude_aborted and (aborted_count > 0 or workspace_count > 0):
            console.print("")
            console.print(f"✨ Cleanup complete: {aborted_count} container(s) + {workspace_count} workspace(s) removed")


def main() -> None:
    """Main entry point."""
    try:
        cli(standalone_mode=False, obj={})
    except KeyboardInterrupt:
        console.print("\n👋 Interrupted by user")
        sys.exit(130)
    except DevsError as e:
        console.print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        # Debug will be handled by each command now
        console.print(f"❌ Unexpected error: {e}")
        # Show traceback if running in development mode (not ideal but safe fallback)
        if os.environ.get('DEVS_DEBUG'):
            raise
        sys.exit(1)


if __name__ == '__main__':
    main()