"""VS Code and external tool integrations."""

import subprocess
import time
from pathlib import Path
from typing import List

from rich.console import Console

from ..exceptions import VSCodeError, DependencyError
from devs_common.core.project import Project
from devs_common.utils.devcontainer import prepare_devcontainer_environment

console = Console()


class VSCodeIntegration:
    """Handles VS Code integration and launching."""
    
    def __init__(self, project: Project) -> None:
        """Initialize VS Code integration.
        
        Args:
            project: Project instance
        """
        self.project = project
        self._check_vscode_cli()
    
    def _check_vscode_cli(self) -> None:
        """Check if VS Code CLI is available.
        
        Raises:
            DependencyError: If code command is not found
        """
        try:
            result = subprocess.run(
                ['code', '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                raise DependencyError(
                    "VS Code 'code' command not found. Make sure VS Code is installed "
                    "and the 'code' command is available in your PATH."
                )
        except FileNotFoundError:
            raise DependencyError(
                "VS Code 'code' command not found. Make sure VS Code is installed "
                "and the 'code' command is available in your PATH."
            )
    
    def generate_devcontainer_uri(self, workspace_dir: Path, dev_name: str, live: bool = False) -> str:
        """Generate VS Code devcontainer URI.
        
        Args:
            workspace_dir: Workspace directory path
            dev_name: Development environment name
            live: Whether to use live mode (mount current directory)
            
        Returns:
            VS Code devcontainer URI
        """
        # Convert workspace path to hex for VS Code URI
        workspace_hex = workspace_dir.as_posix().encode('utf-8').hex()
        
        # Generate workspace name inside container
        # In live mode, use the actual folder name instead of constructed name
        workspace_name = workspace_dir.name if live else self.project.get_workspace_name(dev_name)
        
        # Build VS Code devcontainer URI
        vscode_uri = f"vscode-remote://dev-container+{workspace_hex}/workspaces/{workspace_name}"
        
        return vscode_uri
    
    def launch_devcontainer(
        self, 
        workspace_dir: Path, 
        dev_name: str,
        new_window: bool = True,
        live: bool = False
    ) -> bool:
        """Launch a devcontainer in VS Code.
        
        Args:
            workspace_dir: Workspace directory path
            dev_name: Development environment name 
            new_window: Whether to open in a new window
            live: Whether to use live mode (mount current directory)
            
        Returns:
            True if VS Code launched successfully
            
        Raises:
            VSCodeError: If VS Code launch fails
        """
        try:
            vscode_uri = self.generate_devcontainer_uri(workspace_dir, dev_name, live)
            
            console.print(f"   🚀 Opening VS Code for: {dev_name}")
            
            # Build VS Code command
            cmd = ['code']
            
            if new_window:
                cmd.append('--new-window')
            
            cmd.extend(['--folder-uri', vscode_uri])
            
            # Set environment variables using shared function
            container_workspace_name = self.project.get_workspace_name(dev_name)
            env = prepare_devcontainer_environment(
                dev_name=dev_name,
                project_name=self.project.info.name,
                workspace_folder=workspace_dir,
                container_workspace_name=container_workspace_name,
                git_remote_url=self.project.info.git_remote_url,
                debug=False,  # VS Code launch doesn't need debug mode
                live=live
            )
            
            # Launch VS Code in background
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Give it a moment to start
            time.sleep(1)
            
            # Check if process is still running (not immediately failed)
            if process.poll() is not None and process.returncode != 0:
                raise VSCodeError(f"VS Code process exited with code {process.returncode}")
            
            console.print(f"   ✅ Launched VS Code for: {dev_name}")
            return True
            
        except subprocess.SubprocessError as e:
            raise VSCodeError(f"Failed to launch VS Code for {dev_name}: {e}")
    
    def launch_multiple_devcontainers(
        self, 
        workspace_dirs: List[Path], 
        dev_names: List[str],
        delay_between_windows: float = 2.0,
        live: bool = False
    ) -> int:
        """Launch multiple devcontainers in separate VS Code windows.
        
        Args:
            workspace_dirs: List of workspace directory paths
            dev_names: List of development environment names
            delay_between_windows: Delay between opening windows (seconds)
            live: Whether to use live mode (mount current directory)
            
        Returns:
            Number of successfully launched windows
        """
        if len(workspace_dirs) != len(dev_names):
            raise VSCodeError("Workspace directories and dev names lists must have same length")
        
        console.print(f"📂 Opening {len(dev_names)} devcontainers in VS Code for project: {self.project.info.name}")
        
        success_count = 0
        
        for workspace_dir, dev_name in zip(workspace_dirs, dev_names):
            try:
                if self.launch_devcontainer(workspace_dir, dev_name, new_window=True, live=live):
                    success_count += 1
                
                # Add delay between windows to ensure they open separately
                if delay_between_windows > 0:
                    time.sleep(delay_between_windows)
                    
            except VSCodeError as e:
                console.print(f"   ❌ Failed to launch {dev_name}: {e}")
                continue
        
        if success_count > 0:
            console.print("")
            console.print(f"💡 VS Code windows should open shortly with titles: '<dev-name> - {self.project.info.directory.name}'")
        
        return success_count
    
    def get_vscode_workspace_settings(self, dev_name: str) -> dict:
        """Get VS Code workspace settings for a dev environment.
        
        Args:
            dev_name: Development environment name
            
        Returns:
            Dictionary of workspace settings
        """
        return {
            "settings": {
                "terminal.integrated.defaultProfile.linux": "zsh",
                "python.defaultInterpreterPath": "/usr/local/bin/python",
                "extensions.autoUpdate": False,
            },
            "extensions": {
                "recommendations": [
                    "ms-python.python",
                    "ms-python.pylint",
                    "ms-python.black-formatter",
                    "ms-vscode.vscode-json",
                    "ms-azuretools.vscode-docker",
                ]
            },
            "name": f"{dev_name} - {self.project.info.directory.name}"
        }
    
    def create_vscode_workspace_file(self, workspace_dir: Path, dev_name: str) -> Path:
        """Create VS Code workspace file for a dev environment.
        
        Args:
            workspace_dir: Workspace directory path
            dev_name: Development environment name
            
        Returns:
            Path to created workspace file
        """
        import json
        
        workspace_settings = self.get_vscode_workspace_settings(dev_name)
        workspace_file = workspace_dir / f"{dev_name}.code-workspace"
        
        try:
            with open(workspace_file, 'w', encoding='utf-8') as f:
                json.dump(workspace_settings, f, indent=2)
            
            return workspace_file
            
        except (OSError, json.JSONEncodeError) as e:
            raise VSCodeError(f"Failed to create workspace file for {dev_name}: {e}")


class ExternalToolIntegration:
    """Handles integration with external development tools."""
    
    def __init__(self, project: Project) -> None:
        """Initialize external tool integration.
        
        Args:
            project: Project instance
        """
        self.project = project
    
    def check_dependencies(self) -> dict:
        """Check availability of external dependencies.
        
        Returns:
            Dictionary mapping tool names to availability status
        """
        tools = {
            'docker': ['docker', '--version'],
            'devcontainer': ['devcontainer', '--version'],
            'code': ['code', '--version'],
            'git': ['git', '--version'],
        }
        
        status = {}
        
        for tool_name, cmd in tools.items():
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )
                status[tool_name] = {
                    'available': result.returncode == 0,
                    'version': result.stdout.strip() if result.returncode == 0 else None,
                    'error': result.stderr.strip() if result.returncode != 0 else None
                }
            except FileNotFoundError:
                status[tool_name] = {
                    'available': False,
                    'version': None,
                    'error': 'Command not found'
                }
        
        return status
    
    def print_dependency_status(self) -> None:
        """Print status of all dependencies."""
        status = self.check_dependencies()
        
        console.print("\n🔧 Dependency Status:")
        console.print("─" * 40)
        
        for tool_name, info in status.items():
            if info['available']:
                console.print(f"   ✅ {tool_name}: {info['version']}")
            else:
                console.print(f"   ❌ {tool_name}: {info['error']}")
        
        # Check for missing critical dependencies
        critical_tools = ['docker', 'devcontainer']
        missing_critical = [
            tool for tool in critical_tools 
            if not status.get(tool, {}).get('available', False)
        ]
        
        if missing_critical:
            console.print(f"\n⚠️  Missing critical dependencies: {', '.join(missing_critical)}")
            console.print("   Please install missing tools before using devs.")
        else:
            console.print("\n✅ All critical dependencies are available.")
    
    def get_missing_dependencies(self) -> List[str]:
        """Get list of missing critical dependencies.
        
        Returns:
            List of missing tool names
        """
        status = self.check_dependencies()
        critical_tools = ['docker', 'devcontainer']
        
        return [
            tool for tool in critical_tools
            if not status.get(tool, {}).get('available', False)
        ]