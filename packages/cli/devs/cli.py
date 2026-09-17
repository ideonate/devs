"""Command-line interface for devs package."""

import os
import sys
import subprocess
import traceback
from functools import wraps
from typing import Callable, Sequence
from importlib.metadata import version, PackageNotFoundError

import click
from rich.console import Console
from rich.table import Table

from .config import config
from .core import Project, ContainerManager, WorkspaceManager
from .core.integration import VSCodeIntegration, ExternalToolIntegration
from devs_common.agents import AgentSpec, get_agent
from devs_common.devs_config import DevsConfigLoader
from devs_common.utils.repo_cache import RepoCache
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
    try:
        project = Project()
    except Exception:
        # Outside a git repo (e.g. using --repo), use a dummy project
        project = None
    integration = ExternalToolIntegration(project)
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
    """Get project instance with error handling.

    If the CLI was invoked with --repo, the repo is cloned/updated
    into the local cache and the Project is created from that path.
    Otherwise, the current working directory is used.
    """
    # Check for --repo from the CLI group context
    repo = None
    try:
        ctx = click.get_current_context()
        repo = ctx.obj.get('REPO') if ctx.obj else None
    except RuntimeError:
        pass

    try:
        if repo:
            repo_cache = RepoCache(cache_dir=config.repo_cache_dir)
            repo_path = repo_cache.ensure_repo(repo)
            project = Project(project_dir=repo_path)
        else:
            project = Project()
        return project
    except (ProjectNotFoundError, DevsError) as e:
        console.print(f"❌ {e}")
        sys.exit(1)


def _get_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version info for devs-cli and installed dependencies."""
    if not value or ctx.resilient_parsing:
        return
    parts = []
    for pkg, label in [("devs-cli", "devs-cli"), ("devs-common", "devs-common"), ("devs-webhook", "devs-webhook")]:
        try:
            parts.append(f"{label} {version(pkg)}")
        except PackageNotFoundError:
            pass
    click.echo("\n".join(parts) if parts else "devs-cli (unknown version)")
    ctx.exit()


@click.group()
@click.option('--version', is_flag=True, callback=_get_version, expose_value=False, is_eager=True, help='Show version and exit.')
@click.option('--debug', is_flag=True, help='Show debug tracebacks on error')
@click.option('--repo', default=None, help='GitHub org/repo (e.g. "ideonate/devs") to clone into cache instead of using CWD')
@click.pass_context
def cli(ctx, debug: bool, repo: str) -> None:
    """DevContainer Management Tool

    Manage multiple named devcontainers for any project.
    """
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug
    ctx.obj['REPO'] = repo


@cli.command()
@click.argument('dev_names', nargs=-1, required=True)
@click.option('--rebuild', is_flag=True, help='Force rebuild of container images')
@click.option('--rebuild-if-changed', 'rebuild_if_changed', is_flag=True, help='Rebuild if devcontainer files have changed since last build')
@click.option('--live', is_flag=True, help='Mount current directory as workspace instead of copying')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def start(dev_names: tuple, rebuild: bool, rebuild_if_changed: bool, live: bool, env: tuple, debug: bool) -> None:
    """Start named devcontainers.

    DEV_NAMES: One or more development environment names to start

    Example: devs start sally bob
    Example: devs start sally --live  # Mount current directory directly
    Example: devs start sally --rebuild-if-changed  # Rebuild only if devcontainer files changed
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

            # Ensure container is running.
            # --rebuild: always force a full rebuild
            # --rebuild-if-changed: rebuild only when devcontainer file content has changed
            # (default): never auto-rebuild
            if container_manager.ensure_container_running(
                dev_name,
                workspace_dir,
                force_rebuild=rebuild,
                check_rebuild=rebuild_if_changed,
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
@click.option(
    '--ssh',
    'ssh_host',
    default=None,
    envvar='DEVS_SSH_HOST',
    help=(
        'Open VS Code via direct Remote-SSH into a container ALREADY RUNNING and '
        'reachable at this SSH host (e.g. its Tailscale name). The container is its '
            'own ssh host, so this opens its /workspaces folder directly — no attach. '
        'Connection-only: it does NOT create, start, or sync the container — start it '
            'yourself first (e.g. `devs start` on the host). '
        'Usually unnecessary: without --ssh, `devs vscode <dev>` auto-discovers the '
            "container's tailnet name via the handshake start-tailscale.sh writes. "
        'Can also be set via the DEVS_SSH_HOST env var or ssh_host in DEVS.yml.'
    ),
)
@debug_option
def vscode(dev_names: tuple, delay: float, live: bool, env: tuple, ssh_host: str, debug: bool) -> None:
    """Open devcontainers in VS Code.

    DEV_NAMES: One or more development environment names to open

    Example: devs vscode sally bob
    Example: devs vscode sally --live  # Start with current directory mounted
    Example: devs vscode sally --env QUART_PORT=5001
    Example: devs vscode sally  # Auto: direct Remote-SSH if sally's container is on the tailnet, else local
    Example: devs vscode sally --ssh devs-myorg-myrepo-sally  # Force direct Remote-SSH into that node
    """
    check_dependencies()
    project = get_project()

    # If --ssh not given on CLI or env, check DEVS.yml
    if not ssh_host:
        ssh_host = DevsConfigLoader.load_ssh_host(project.info.name) or None

    vscode_integration = VSCodeIntegration(project)

    # Decide, per dev, whether to open via direct Remote-SSH (the container is its
    # own tailnet ssh host) or to manage it locally. An explicit --ssh / env / DEVS.yml
    # host forces SSH for every dev; otherwise auto-discover via the tailnet handshake
    # that start-tailscale.sh writes (set only when the container is up + Tailscale SSH
    # is on). Devs that don't resolve fall through to normal local mode.
    if ssh_host:
        ssh_hosts = {dev_name: ssh_host for dev_name in dev_names}
    else:
        ssh_hosts = {}
        for dev_name in dev_names:
            host = vscode_integration.resolve_tailnet_ssh_host(dev_name)
            if host:
                ssh_hosts[dev_name] = host

    ssh_dev_names = [d for d in dev_names if d in ssh_hosts]
    local_dev_names = [d for d in dev_names if d not in ssh_hosts]

    # --- Direct Remote-SSH (attach-only: container already running on its host) ---
    if ssh_dev_names:
        for dev_name in ssh_dev_names:
            console.print(f"   🔗 {dev_name} → ssh://{ssh_hosts[dev_name]} (direct Remote-SSH into container)")
        # Synthetic workspace Paths: only the name is used to build the URI; the path
        # is never accessed locally in SSH mode.
        workspace_dirs = [config.workspaces_dir / project.get_workspace_name(d) for d in ssh_dev_names]
        try:
            success_count = vscode_integration.launch_multiple_devcontainers(
                workspace_dirs,
                ssh_dev_names,
                delay_between_windows=delay,
                live=live,
                ssh_hosts=ssh_hosts,
            )
            if success_count == 0:
                console.print("❌ Failed to open any VS Code windows (Remote-SSH)")
        except VSCodeError as e:
            console.print(f"❌ VS Code integration error: {e}")

    # --- Local mode: manage containers and workspaces as normal ---
    if local_dev_names:
        container_manager = ContainerManager(project, config)
        workspace_manager = WorkspaceManager(project, config)

        workspace_dirs = []
        valid_dev_names = []

        for dev_name in local_dev_names:
            console.print(f"   Preparing: {dev_name}")

            devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
            cli_env = parse_env_vars(env) if env else {}
            extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None

            if extra_env:
                console.print(f"🔧 Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")

            try:
                workspace_dir = workspace_manager.create_workspace(dev_name, live=live)

                if container_manager.ensure_container_running(dev_name, workspace_dir, check_rebuild=False, debug=debug, live=live, extra_env=extra_env):
                    workspace_dirs.append(workspace_dir)
                    valid_dev_names.append(dev_name)
                else:
                    console.print(f"   ❌ Failed to start container for {dev_name}, skipping...")

            except (ContainerError, WorkspaceError) as e:
                console.print(f"   ❌ Error preparing {dev_name}: {e}")
                continue

        if workspace_dirs:
            try:
                success_count = vscode_integration.launch_multiple_devcontainers(
                    workspace_dirs,
                    valid_dev_names,
                    delay_between_windows=delay,
                    live=live,
                )

                if success_count == 0:
                    console.print("❌ Failed to open any VS Code windows")

            except VSCodeError as e:
                console.print(f"❌ VS Code integration error: {e}")


@cli.command()
@click.argument('dev_names', nargs=-1, required=True) 
def stop(dev_names: tuple) -> None:
    """Stop devcontainers (preserves container state for restart).

    Use 'devs clean' to remove containers entirely.

    DEV_NAMES: One or more development environment names to stop

    Example: devs stop sally
    """
    check_dependencies()
    project = get_project()

    console.print(f"🛑 Stopping devcontainers for project: {project.info.name}")

    container_manager = ContainerManager(project, config)

    for dev_name in dev_names:
        console.print(f"   Stopping: {dev_name}")
        container_manager.stop_container(dev_name, remove=False)


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

        # Open shell (ensure_container_running is called internally)
        container_manager.exec_shell(dev_name, workspace_dir, debug=debug, live=live)
        
    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error opening shell for {dev_name}: {e}")
        sys.exit(1)


def _run_agent(agent: AgentSpec, dev_name: str, prompt: str, reset_workspace: bool, live: bool, env: tuple, debug: bool) -> None:
    """Run a coding agent against a prompt in a devcontainer, streaming its output."""
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

        # Execute the agent (ensure_container_running is called internally)
        console.print(f"🤖 Executing {agent.display_name} in {dev_name}...")
        if reset_workspace and not live:
            console.print("🗑️  Workspace contents reset")
        console.print(f"📝 Prompt: {prompt}")
        console.print("")

        success, output, error, _ = container_manager.exec_agent(
            agent,
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
            console.print(f"✅ {agent.display_name} execution completed")
        else:
            console.print(f"❌ {agent.display_name} execution failed")
            if error:
                console.print("")
                console.print("🚫 Error:")
                console.print(error)
            sys.exit(1)

    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error executing {agent.display_name} in {dev_name}: {e}")
        sys.exit(1)


def _add_agent_command(
    name: str,
    auth_help: str,
    handle_auth: Callable[..., None],
    auth_options: Sequence[Callable] = (),
    auth_examples: Sequence[str] = (),
) -> None:
    """Register a `devs <agent> DEV_NAME PROMPT` command for an agent in devs_common.agents.

    Args:
        name: Agent name in the AGENTS registry
        auth_help: Help text for the --auth flag
        handle_auth: Called for `--auth` with debug= plus any auth_options values
        auth_options: Extra click options that only apply to --auth (e.g. --api-key)
        auth_examples: Extra `devs <agent> --auth ...` example lines for the help text
    """
    agent = get_agent(name)

    def command(dev_name: str, prompt: str, auth: bool, reset_workspace: bool, live: bool,
                env: tuple, debug: bool, **auth_values) -> None:
        if auth:
            handle_auth(debug=debug, **auth_values)
            return
        # Validate required arguments for execution mode
        if not dev_name or not prompt:
            raise click.UsageError("DEV_NAME and PROMPT are required unless using --auth")
        _run_agent(agent, dev_name, prompt, reset_workspace, live, env, debug)

    examples = [
        f'devs {name} sally "Summarize this codebase"',
        f'devs {name} sally "Fix the tests" --reset-workspace',
        f'devs {name} sally "Fix the tests" --live  # Run with current directory',
        f'devs {name} sally "Start the server" --env QUART_PORT=5001',
        f'devs {name} --auth',
        *auth_examples,
    ]
    command.__name__ = name
    command.__doc__ = (
        f"Execute {agent.description} in devcontainer or set up authentication.\n\n"
        f"DEV_NAME: Development environment name\n\n"
        f"PROMPT: Prompt to send to {agent.display_name}\n\n"
        + "\n\n".join(f"Example: {example}" for example in examples)
    )

    decorators = [
        cli.command(name=name),
        click.argument('dev_name', required=False),
        click.argument('prompt', required=False),
        click.option('--auth', is_flag=True, help=auth_help),
        *auth_options,
        click.option('--reset-workspace', is_flag=True, help='Reset workspace contents before execution'),
        click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace'),
        click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)'),
        debug_option,
    ]
    for decorator in reversed(decorators):
        command = decorator(command)


def _show_claude_auth(debug: bool) -> None:
    """Explain how to give devcontainers a Claude token."""
    console.print("🔐 Claude authentication for devcontainers")
    console.print("")
    console.print("1. Generate a token (on a machine with a browser):")
    console.print("   [cyan]claude setup-token[/cyan]")
    console.print("")
    console.print("2. Add the token to your environment:")
    console.print("   [cyan]export CLAUDE_CODE_OAUTH_TOKEN=<token>[/cyan]")
    console.print("")
    console.print("   Or add it to [cyan]~/.devs/envs/default/.env[/cyan]:")
    console.print("   [dim]CLAUDE_CODE_OAUTH_TOKEN=<token>[/dim]")
    console.print("")
    console.print("The token will be automatically passed to all devcontainers.")


def _show_hermes_auth(debug: bool) -> None:
    """Explain how to give devcontainers an OpenRouter key for Hermes."""
    console.print("🔐 Hermes Agent authentication for devcontainers")
    console.print("")
    console.print("Hermes runs against OpenRouter. Create an API key at:")
    console.print("   [cyan]https://openrouter.ai/keys[/cyan]")
    console.print("")
    console.print("Add it to [cyan]~/.devs/envs/default/.env[/cyan] (or a project-specific env dir):")
    console.print("   [dim]OPENROUTER_API_KEY=<key>[/dim]")
    console.print("")
    console.print("The default model is [cyan]z-ai/glm-5.3[/cyan]. To use another OpenRouter model:")
    console.print("   [dim]HERMES_INFERENCE_MODEL=<provider/model>[/dim]")
    console.print("")
    console.print("The env file is mounted into every devcontainer and loaded on each shell.")


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
            console.print(traceback.format_exc())
        sys.exit(1)


_add_agent_command(
    "claude",
    auth_help='Show Claude authentication setup instructions',
    handle_auth=_show_claude_auth,
)
_add_agent_command(
    "codex",
    auth_help='Set up Codex authentication for devcontainers',
    handle_auth=_handle_codex_auth,
    auth_options=[click.option('--api-key', help='OpenAI API key to authenticate with (use with --auth)')],
    auth_examples=['devs codex --auth --api-key <YOUR_KEY>   # API key authentication'],
)
_add_agent_command(
    "hermes",
    auth_help='Show Hermes (OpenRouter) authentication setup instructions',
    handle_auth=_show_hermes_auth,
)


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

        # Execute test command (ensure_container_running is called internally)
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
@click.argument('dev_name')
@click.option('--auth', is_flag=True, help='Set up tunnel authentication (per-container, persists across restarts)')

@click.option('--status', is_flag=True, help='Check tunnel status instead of starting')
@click.option('--kill', 'kill_tunnel', is_flag=True, help='Kill running tunnel')
@click.option('--live', is_flag=True, help='Start container with current directory mounted as workspace')
@click.option('--env', multiple=True, help='Environment variables to pass to container (format: VAR=value)')
@debug_option
def tunnel(dev_name: str, auth: bool, status: bool, kill_tunnel: bool, live: bool, env: tuple, debug: bool) -> None:
    """Start a VS Code tunnel in devcontainer.

    VS Code tunnels allow you to connect VS Code directly to the container
    without SSH - the container initiates an outbound connection to Microsoft's
    tunnel service, and your local VS Code connects through that.

    First-time setup requires authentication per container:
      devs tunnel <name> --auth

    Auth is stored in the container and persists across stop/restart
    cycles (but not container removal).

    DEV_NAME: Development environment name

    Example: devs tunnel sally --auth    # One-time auth setup
    Example: devs tunnel sally           # Start tunnel (background)
    Example: devs tunnel sally --status  # Check tunnel status
    Example: devs tunnel sally --kill    # Stop running tunnel
    """
    check_dependencies()
    project = get_project()

    # Load environment variables from DEVS.yml and merge with CLI --env flags
    devs_env = DevsConfigLoader.load_env_vars(dev_name, project.info.name)
    cli_env = parse_env_vars(env) if env else {}
    extra_env = merge_env_vars(devs_env, cli_env) if devs_env or cli_env else None

    if extra_env:
        console.print(f"Environment variables: {', '.join(f'{k}={v}' for k, v in extra_env.items())}")

    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)

    try:
        # Ensure workspace exists (handles live mode internally)
        workspace_dir = workspace_manager.create_workspace(dev_name, live=live)

        if auth:
            # Interactive authentication inside the container
            container_manager.tunnel_auth(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                debug=debug,
                live=live,
                extra_env=extra_env
            )

        elif status:
            # Check tunnel status
            is_running, status_msg = container_manager.get_tunnel_status(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                debug=debug,
                live=live,
                extra_env=extra_env
            )
            if is_running:
                console.print(f"[bold]Tunnel for {dev_name}:[/bold]")
                console.print(status_msg)
            else:
                console.print(f"[bold]Tunnel for {dev_name}:[/bold]")
                console.print(f"[dim]   Not running[/dim]")
                if status_msg:
                    console.print(f"   {status_msg}")

        elif kill_tunnel:
            # Kill the tunnel
            console.print(f"Stopping tunnel in {dev_name}...")
            container_manager.kill_tunnel(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                debug=debug,
                live=live,
                extra_env=extra_env
            )

        else:
            # Start the tunnel (background)
            container_manager.start_tunnel(
                dev_name=dev_name,
                workspace_dir=workspace_dir,
                debug=debug,
                live=live,
                extra_env=extra_env
            )

    except (ContainerError, WorkspaceError) as e:
        console.print(f"Error with tunnel for {dev_name}: {e}")
        sys.exit(1)



@cli.command()
@click.option('--all-projects', is_flag=True, help='List containers for all projects')
def list(all_projects: bool) -> None:
    """List active devcontainers for current project."""
    check_dependencies() 
    
    if all_projects:
        console.print("📋 All devcontainers:")
        console.print("")

        try:
            containers = ContainerManager.list_all_containers()

            if not containers:
                console.print("   No active devcontainers found")
                return

            table = Table()
            table.add_column("Project", style="magenta")
            table.add_column("Name", style="cyan")
            table.add_column("Mode", style="yellow")
            table.add_column("Status", style="green")
            table.add_column("Container", style="dim")
            table.add_column("Created", style="dim")

            for container in containers:
                created_str = container.created.strftime("%Y-%m-%d %H:%M") if container.created else "unknown"
                mode = "live" if container.labels.get('devs.live') == 'true' else "copy"
                table.add_row(
                    container.project_name,
                    container.dev_name,
                    mode,
                    container.status,
                    container.name,
                    created_str
                )

            console.print(table)

        except ContainerError as e:
            console.print(f"❌ Error listing containers: {e}")
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
        project = get_project()
        
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