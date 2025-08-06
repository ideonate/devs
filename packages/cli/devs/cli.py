"""Command-line interface for devs package."""

import sys
from pathlib import Path
from typing import List

import click
from rich.console import Console
from rich.table import Table

from .config import config
from .core import Project, ContainerManager, WorkspaceManager
from .core.integration import VSCodeIntegration, ExternalToolIntegration
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
@click.pass_context
def start(ctx, dev_names: tuple, rebuild: bool) -> None:
    """Start named devcontainers.
    
    DEV_NAMES: One or more development environment names to start
    
    Example: devs start sally bob
    """
    check_dependencies()
    project = get_project()
    debug = ctx.obj.get('DEBUG', False)
    
    console.print(f"🚀 Starting devcontainers for project: {project.info.name}")
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    for dev_name in dev_names:
        console.print(f"   Starting: {dev_name}")
        
        try:
            # Create/ensure workspace exists
            workspace_dir = workspace_manager.create_workspace(dev_name)
            
            # Ensure container is running
            if container_manager.ensure_container_running(
                dev_name, 
                workspace_dir, 
                force_rebuild=rebuild,
                debug=debug
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
@click.pass_context
def vscode(ctx, dev_names: tuple, delay: float) -> None:
    """Open devcontainers in VS Code.
    
    DEV_NAMES: One or more development environment names to open
    
    Example: devs vscode sally bob
    """
    check_dependencies()
    project = get_project()
    debug = ctx.obj.get('DEBUG', False)
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    vscode = VSCodeIntegration(project)
    
    workspace_dirs = []
    valid_dev_names = []
    
    for dev_name in dev_names:
        console.print(f"   Preparing: {dev_name}")
        
        try:
            # Ensure workspace exists
            workspace_dir = workspace_manager.create_workspace(dev_name)
            
            # Ensure container is running
            if container_manager.ensure_container_running(dev_name, workspace_dir, debug=debug):
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
                delay_between_windows=delay
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
@click.pass_context
def shell(ctx, dev_name: str) -> None:
    """Open shell in devcontainer.
    
    DEV_NAME: Development environment name
    
    Example: devs shell sally
    """
    check_dependencies()
    project = get_project()
    debug = ctx.obj.get('DEBUG', False)
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    try:
        # Ensure workspace exists
        workspace_dir = workspace_manager.create_workspace(dev_name)
        
        # Open shell
        container_manager.exec_shell(dev_name, workspace_dir, debug=debug)
        
    except (ContainerError, WorkspaceError) as e:
        console.print(f"❌ Error opening shell for {dev_name}: {e}")
        sys.exit(1)


@cli.command()
@click.argument('dev_name')
@click.argument('prompt')
@click.option('--reset-workspace', is_flag=True, help='Reset workspace contents before execution')
@click.pass_context
def claude(ctx, dev_name: str, prompt: str, reset_workspace: bool) -> None:
    """Execute Claude CLI in devcontainer.
    
    DEV_NAME: Development environment name
    PROMPT: Prompt to send to Claude
    
    Example: devs claude sally "Summarize this codebase"
    Example: devs claude sally "Fix the tests" --reset-workspace
    """
    check_dependencies()
    project = get_project()
    debug = ctx.obj.get('DEBUG', False)
    
    container_manager = ContainerManager(project, config)
    workspace_manager = WorkspaceManager(project, config)
    
    try:
        # Ensure workspace exists
        workspace_dir = workspace_manager.create_workspace(dev_name, reset_contents=reset_workspace)
        
        # Execute Claude
        console.print(f"🤖 Executing Claude in {dev_name}...")
        if reset_workspace:
            console.print("🗑️  Workspace contents reset")
        console.print(f"📝 Prompt: {prompt}")
        console.print("")
        
        success, output, error = container_manager.exec_claude(
            dev_name, workspace_dir, prompt, debug=debug, stream=True
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
        table.add_column("Status", style="green")
        table.add_column("Container", style="dim")
        table.add_column("Created", style="dim")
        
        for container in containers:
            created_str = container.created.strftime("%Y-%m-%d %H:%M") if container.created else "unknown"
            table.add_row(
                container.dev_name,
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
    ctx = click.Context(cli, obj={})
    try:
        cli.main(standalone_mode=False, obj=ctx.obj)
    except KeyboardInterrupt:
        console.print("\n👋 Interrupted by user")
        sys.exit(130)
    except DevsError as e:
        console.print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        debug = ctx.obj.get('DEBUG', False)
        console.print(f"❌ Unexpected error: {e}")
        if debug:
            raise
        sys.exit(1)


if __name__ == '__main__':
    main()