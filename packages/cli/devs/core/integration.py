"""VS Code and external tool integrations."""

import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from ..exceptions import VSCodeError
from devs_common.core.project import Project
from devs_common.utils.config_hash import get_env_mount_path
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
        self.code_available = self._check_vscode_cli()

    def _check_vscode_cli(self) -> bool:
        """Check if the VS Code 'code' CLI is available.

        This is intentionally non-fatal: on a remote/headless dev box (e.g. one you
        only ever reach over SSH) there may be no local 'code' command, but it is still
        useful to start the container and print the URI / command you'd run from a
        machine that does have VS Code. Callers consult ``self.code_available`` and fall
        back to printing the command instead of launching.

        Returns:
            True if the 'code' command is available, False otherwise.
        """
        try:
            result = subprocess.run(
                ['code', '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def resolve_tailnet_ssh_host(self, dev_name: str) -> Optional[str]:
        """Discover a container's own tailnet SSH name via the writeback handshake.

        Joins docker <-> tailnet by docker container id, WITHOUT `docker exec`:
        ``docker inspect`` the container for its hostname (== its short container id,
        == the ``$HOSTNAME`` start-tailscale.sh keyed its handshake file by), then read
        that file out of the host-shared env mount. Returns the short MagicDNS name
        (e.g. ``devs-acme-app-eamonn-1``) only when the container is up AND Tailscale
        SSH is on; otherwise None (caller falls back to local mode).
        """
        container_name = self.project.get_container_name(dev_name)
        try:
            inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{.Config.Hostname}}", container_name],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            return None  # no docker here
        if inspect.returncode != 0:
            return None  # container doesn't exist / not inspectable
        container_id = inspect.stdout.strip()
        if not container_id:
            return None

        handshake = get_env_mount_path(self.project.info.name) / "ts-nodes" / f"{container_id}.json"
        if not handshake.exists():
            return None
        try:
            data = json.loads(handshake.read_text())
        except (OSError, ValueError):
            return None
        if not data.get("ssh"):
            return None  # on the tailnet but not accepting SSH
        return data.get("short") or None

    def generate_devcontainer_uri(
        self,
        workspace_dir: Path,
        dev_name: str,
        live: bool = False,
        attach_to_existing: bool = True,
        ssh_host: Optional[str] = None,
    ) -> str:
        """Generate VS Code devcontainer URI.

        Args:
            workspace_dir: Workspace directory path
            dev_name: Development environment name
            live: Whether to use live mode (mount current directory)
            attach_to_existing: Whether to attach to existing container (vs create new one)
            ssh_host: If set, generate a plain Remote-SSH folder URI for this host.
                      In the devs+Tailscale model the container IS its own SSH host
                      (you SSH straight into it — there's no separate Docker daemon to
                      attach through), so this is NOT an attached-container URI.

        Returns:
            VS Code devcontainer URI
        """
        # IMPORTANT: In live mode, use the actual host folder name because devcontainer CLI
        # mounts the host directory directly and VS Code must match that path.
        workspace_name = workspace_dir.name if live else self.project.get_workspace_name(dev_name)

        if ssh_host:
            # Direct Remote-SSH INTO the container. With Tailscale the container is its
            # own tailnet node running Tailscale SSH, so VS Code opens the in-container
            # workspace folder over SSH — no Docker host, no attach. Wrapping this in an
            # attached-container URI would make VS Code SSH in and then hunt for a Docker
            # daemon that isn't there.
            return f"vscode-remote://ssh-remote+{ssh_host}/workspaces/{workspace_name}"

        if attach_to_existing:
            container_name = self.project.get_container_name(dev_name)
            container_hex = container_name.encode("utf-8").hex()
            return f"vscode-remote://attached-container+{container_hex}/workspaces/{workspace_name}"

        # Create new container from devcontainer.json
        workspace_hex = workspace_dir.as_posix().encode("utf-8").hex()
        return f"vscode-remote://dev-container+{workspace_hex}/workspaces/{workspace_name}"

    def _format_code_command(
        self,
        workspace_dir: Path,
        dev_name: str,
        live: bool,
        new_window: bool,
        ssh_host: Optional[str],
    ) -> str:
        """Build the 'code' command string for opening a container.

        Returned as a copy/paste-ready, shell-quoted string so it can be printed and
        run from another machine that has VS Code installed.
        """
        vscode_uri = self.generate_devcontainer_uri(
            workspace_dir, dev_name, live, attach_to_existing=True, ssh_host=ssh_host
        )
        cmd = ["code"]
        if new_window:
            cmd.append("--new-window")
        cmd.extend(["--folder-uri", vscode_uri])
        return " ".join(shlex.quote(part) for part in cmd)

    def _print_code_commands(
        self,
        workspace_dir: Path,
        dev_name: str,
        live: bool,
        new_window: bool,
        ssh_host: Optional[str],
    ) -> None:
        """Print the 'code' command for this container.

        When an SSH host is set we print only the Remote-SSH command (the plain
        attached-container command wouldn't work from another machine and is just
        noise). Otherwise we print the local attached-container command.
        """
        if ssh_host:
            ssh_cmd = self._format_code_command(workspace_dir, dev_name, live, new_window, ssh_host)
            console.print(f"   📋 VS Code command (Remote-SSH: {ssh_host}):")
            console.print(f"      {ssh_cmd}")
            return

        plain_cmd = self._format_code_command(workspace_dir, dev_name, live, new_window, None)
        console.print(f"   📋 VS Code command:")
        console.print(f"      {plain_cmd}")

    def launch_devcontainer(
        self,
        workspace_dir: Path,
        dev_name: str,
        new_window: bool = True,
        live: bool = False,
        ssh_host: Optional[str] = None,
    ) -> bool:
        """Launch a devcontainer in VS Code.

        Args:
            workspace_dir: Workspace directory path
            dev_name: Development environment name
            new_window: Whether to open in a new window
            live: Whether to use live mode (mount current directory)
            ssh_host: If set, connect via Remote-SSH to this host then attach to the container.

        Returns:
            True if VS Code launched successfully

        Raises:
            VSCodeError: If VS Code launch fails
        """
        try:
            vscode_uri = self.generate_devcontainer_uri(
                workspace_dir, dev_name, live, attach_to_existing=True, ssh_host=ssh_host
            )

            cmd = ["code"]

            if new_window:
                cmd.append("--new-window")

            cmd.extend(["--folder-uri", vscode_uri])

            # Always print the command(s) so they can be copied and run elsewhere.
            self._print_code_commands(workspace_dir, dev_name, live, new_window, ssh_host)

            # No local 'code' command (e.g. a headless remote dev box reached over SSH):
            # don't fail — just point to the command printed above and stop here.
            if not self.code_available:
                if ssh_host:
                    # SSH mode is attach-only: we never created/started the container,
                    # so we can't claim it's ready. The user must ensure it's running
                    # on the remote host themselves.
                    console.print(
                        f"   ⚠️  VS Code 'code' command not found here — printed the attach "
                        f"URI only. Make sure the container is already running on '{ssh_host}', "
                        "then run the command above from a machine with VS Code installed."
                    )
                else:
                    console.print(
                        f"   ⚠️  VS Code 'code' command not found here — container is ready, "
                        "but VS Code can't be launched from this machine. "
                        "Run the command above from a machine with VS Code installed."
                    )
                return True

            if ssh_host:
                console.print(f"   🚀 Opening VS Code for: {dev_name} (via SSH: {ssh_host})")
            else:
                console.print(f"   🚀 Opening VS Code for: {dev_name}")

            # Set environment variables using shared function
            container_workspace_name = self.project.get_workspace_name(dev_name)
            env = prepare_devcontainer_environment(
                dev_name=dev_name,
                project_name=self.project.info.name,
                workspace_folder=workspace_dir,
                container_workspace_name=container_workspace_name,
                git_remote_url=self.project.info.git_remote_url,
                debug=False,
                live=live,
            )

            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            time.sleep(1)

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
        live: bool = False,
        ssh_host: Optional[str] = None,
        ssh_hosts: Optional[dict] = None,
    ) -> int:
        """Launch multiple devcontainers in separate VS Code windows.

        Args:
            workspace_dirs: List of workspace directory paths
            dev_names: List of development environment names
            delay_between_windows: Delay between opening windows (seconds)
            live: Whether to use live mode (mount current directory)
            ssh_host: If set, connect every dev via direct Remote-SSH to this host.
            ssh_hosts: Optional per-dev override mapping ``dev_name -> ssh host``
                (each container is its own tailnet host, so they differ). Falls back
                to ``ssh_host`` for any dev not present in the map.

        Returns:
            Number of successfully launched windows
        """
        if len(workspace_dirs) != len(dev_names):
            raise VSCodeError("Workspace directories and dev names lists must have same length")

        ssh_hosts = ssh_hosts or {}
        if ssh_host or ssh_hosts:
            console.print(
                f"📂 Opening {len(dev_names)} devcontainers in VS Code "
                f"(via Remote-SSH) for project: {self.project.info.name}"
            )
        else:
            console.print(f"📂 Opening {len(dev_names)} devcontainers in VS Code for project: {self.project.info.name}")

        success_count = 0

        for workspace_dir, dev_name in zip(workspace_dirs, dev_names):
            host = ssh_hosts.get(dev_name, ssh_host)
            try:
                if self.launch_devcontainer(
                    workspace_dir, dev_name, new_window=True, live=live, ssh_host=host
                ):
                    success_count += 1

                if delay_between_windows > 0:
                    time.sleep(delay_between_windows)

            except VSCodeError as e:
                console.print(f"   ❌ Failed to launch {dev_name}: {e}")
                continue

        if success_count > 0 and self.code_available:
            console.print("")
            console.print(f"💡 VS Code windows should open shortly with titles: '<dev-name> - {self.project.info.directory.name}'")

        return success_count
    
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