"""API routes for webadmin."""

import asyncio
import re
import subprocess
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

from devs_common.core.container import ContainerManager
from devs_common.core.workspace import WorkspaceManager
from devs_common.core.project import Project
from devs_common.utils.repo_cache import RepoCache
from devs_common.utils.docker_client import DockerClient
from devs_common.devs_config import DevsConfigLoader
from devs_common.exceptions import DevsError

from ..config import config

logger = structlog.get_logger()

router = APIRouter(prefix="/api")

# Track running tunnel auth processes: container_name -> subprocess.Popen
_auth_processes: Dict[str, subprocess.Popen] = {}


class StartRequest(BaseModel):
    repo: str  # org/repo format
    dev_name: str


class ContainerActionRequest(BaseModel):
    container_name: str  # Docker container name from list


def _get_repo_project(repo: str) -> Project:
    """Clone/update a repo via cache and return a Project for it."""
    repo_cache = RepoCache(cache_dir=config.repo_cache_dir)
    repo_path = repo_cache.ensure_repo(repo)
    return Project(project_dir=repo_path)


@router.get("/containers")
async def list_containers(repo: Optional[str] = None) -> dict:
    """List containers, optionally filtered by repo."""
    try:
        if repo:
            project = await asyncio.to_thread(_get_repo_project, repo)
            container_manager = ContainerManager(project, config)
            containers = await asyncio.to_thread(container_manager.list_containers)
        else:
            containers = await asyncio.to_thread(ContainerManager.list_all_containers)

        return {
            "containers": [
                {
                    "name": c.name,
                    "dev_name": c.dev_name,
                    "project_name": c.project_name,
                    "status": c.status,
                    "container_id": c.container_id,
                    "created": c.created.isoformat() if c.created else None,
                    "mode": "live" if c.labels.get("devs.live") == "true" else "copy",
                }
                for c in containers
            ]
        }
    except DevsError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/start")
async def start_container(request: StartRequest) -> dict:
    """Start a named devcontainer for a repo."""
    try:
        project = await asyncio.to_thread(_get_repo_project, request.repo)
        container_manager = ContainerManager(project, config)
        workspace_manager = WorkspaceManager(project, config)

        devs_env = DevsConfigLoader.load_env_vars(request.dev_name, project.info.name)
        extra_env = devs_env if devs_env else None

        workspace_dir = await asyncio.to_thread(
            workspace_manager.create_workspace, request.dev_name
        )

        success = await asyncio.to_thread(
            container_manager.ensure_container_running,
            request.dev_name,
            workspace_dir,
            extra_env=extra_env,
        )

        if success:
            return {
                "status": "started",
                "repo": request.repo,
                "dev_name": request.dev_name,
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to start container")

    except DevsError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _stop_by_name(container_name: str, remove: bool) -> bool:
    """Stop (and optionally remove) a container by its Docker name."""
    docker = DockerClient()
    try:
        docker.stop_container(container_name)
    except Exception:
        return False
    if remove:
        try:
            docker.remove_container(container_name)
        except Exception:
            pass
    return True


def _clean_workspace(project_name: str, dev_name: str) -> None:
    """Remove workspace for a project/dev combination."""
    # Build workspace path directly from project name + dev name
    workspace_name = f"{project_name}-{dev_name}"
    workspace_dir = config.workspaces_dir / workspace_name
    if workspace_dir.exists():
        import shutil
        shutil.rmtree(workspace_dir)


@router.post("/restart")
async def restart_container(request: ContainerActionRequest) -> dict:
    """Restart a stopped container by Docker name."""
    def _restart(container_name: str) -> bool:
        docker = DockerClient()
        try:
            docker.start_container(container_name)
            return True
        except Exception:
            return False

    success = await asyncio.to_thread(_restart, request.container_name)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Container {request.container_name} not found or cannot be started",
        )

    return {"status": "started", "container_name": request.container_name}


@router.post("/stop")
async def stop_container(request: ContainerActionRequest) -> dict:
    """Stop a container by Docker name (preserves state)."""
    success = await asyncio.to_thread(_stop_by_name, request.container_name, False)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Container {request.container_name} not found or already stopped",
        )

    return {"status": "stopped", "container_name": request.container_name}


@router.post("/clean")
async def clean_container(request: ContainerActionRequest) -> dict:
    """Stop, remove container and clean workspace by Docker name."""
    # Get container labels before removing so we can find the workspace
    docker = DockerClient()
    dev_name = None
    project_name = None
    try:
        containers = docker.find_containers_by_labels({"devs.managed": "true"})
        for c in containers:
            if c["name"] == request.container_name:
                dev_name = c["labels"].get("devs.dev")
                project_name = c["labels"].get("devs.project")
                break
    except Exception:
        pass

    # Stop and remove the container
    await asyncio.to_thread(_stop_by_name, request.container_name, True)

    # Clean workspace if we found the labels
    if dev_name and project_name:
        await asyncio.to_thread(_clean_workspace, project_name, dev_name)

    return {"status": "cleaned", "container_name": request.container_name}


# --- Tunnel helpers ---

def _get_container_labels(container_name: str) -> dict:
    """Get labels for a container by Docker name."""
    docker = DockerClient()
    containers = docker.find_containers_by_labels({"devs.managed": "true"})
    for c in containers:
        if c["name"] == container_name:
            return c.get("labels", {})
    return {}


def _make_tunnel_name(container_name: str) -> str:
    """Derive tunnel name from container name (max 20 chars).

    Container names are like dev-ideonate-devs-sally.
    Tunnel name uses the same convention, truncated to 20 chars
    keeping the dev name suffix.
    """
    name = container_name.replace(".", "-").replace("_", "-")
    if len(name) <= 20:
        return name
    # Keep the last segment (dev name) and truncate the rest
    parts = name.rsplit("-", 1)
    if len(parts) == 2:
        suffix = f"-{parts[1]}"
        budget = 20 - len(suffix)
        if budget >= 3:
            return parts[0][:budget].rstrip("-") + suffix
    return name[:20]


def _docker_exec(container_name: str, cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a docker exec command."""
    full_cmd = ["docker", "exec", container_name] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)


# --- Tunnel endpoints ---

@router.get("/tunnel/status")
async def tunnel_status(container_name: str) -> dict:
    """Get VS Code tunnel status for a container."""
    try:
        result = await asyncio.to_thread(
            _docker_exec, container_name,
            ["/usr/local/bin/code", "tunnel", "status"]
        )
        is_running = result.returncode == 0
        tunnel_name = _make_tunnel_name(container_name)
        return {
            "running": is_running,
            "message": result.stdout.strip() if is_running else (result.stderr.strip() or "No tunnel running"),
            "tunnel_name": tunnel_name,
        }
    except subprocess.TimeoutExpired:
        return {"running": False, "message": "Status check timed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/start")
async def tunnel_start(request: ContainerActionRequest) -> dict:
    """Start a VS Code tunnel in a container (background)."""
    container_name = request.container_name
    tunnel_name = _make_tunnel_name(container_name)
    log_file = "/tmp/vscode-tunnel.log"
    tunnel_cmd = f"/usr/local/bin/code tunnel --accept-server-license-terms --name {tunnel_name}"

    def _start() -> dict:
        # Start tunnel in background
        subprocess.run(
            ["docker", "exec", "-d", container_name,
             "/bin/sh", "-c", f"{tunnel_cmd} > {log_file} 2>&1"],
            check=True,
        )

        # Poll for startup (up to 15s)
        import time
        for i in range(15):
            time.sleep(1)
            result = subprocess.run(
                ["docker", "exec", container_name, "cat", log_file],
                capture_output=True, text=True,
            )
            output = result.stdout

            if "Open this link" in output or "vscode.dev/tunnel" in output:
                return {
                    "status": "running",
                    "tunnel_name": tunnel_name,
                    "web_url": f"https://vscode.dev/tunnel/{tunnel_name}",
                    "vscode_cmd": f"code --remote tunnel+{tunnel_name}",
                }

            if "log in" in output.lower() or "device" in output.lower() or "invalid" in output.lower():
                # Auth needed - kill the failed attempt
                subprocess.run(
                    ["docker", "exec", container_name, "/usr/local/bin/code", "tunnel", "kill"],
                    capture_output=True,
                )
                return {"status": "auth_required", "tunnel_name": tunnel_name}

        # Timeout - tunnel may still be starting
        return {
            "status": "starting",
            "tunnel_name": tunnel_name,
            "message": "Tunnel may still be starting, check status",
        }

    try:
        return await asyncio.to_thread(_start)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/kill")
async def tunnel_kill(request: ContainerActionRequest) -> dict:
    """Kill a running VS Code tunnel."""
    try:
        result = await asyncio.to_thread(
            _docker_exec, request.container_name,
            ["/usr/local/bin/code", "tunnel", "kill"]
        )
        return {
            "killed": result.returncode == 0,
            "message": result.stdout.strip() or result.stderr.strip(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/auth")
async def tunnel_auth_start(request: ContainerActionRequest) -> dict:
    """Start tunnel auth (GitHub device flow).

    Launches the login command, captures the device URL + code,
    and returns them so the user can complete auth in their browser.
    The process keeps running until auth completes or is cancelled.
    """
    container_name = request.container_name

    # Kill any existing auth process for this container
    if container_name in _auth_processes:
        try:
            _auth_processes[container_name].kill()
        except Exception:
            pass
        del _auth_processes[container_name]

    def _start_auth() -> dict:
        proc = subprocess.Popen(
            ["docker", "exec", container_name,
             "/usr/local/bin/code", "tunnel", "user", "login",
             "--provider", "github"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _auth_processes[container_name] = proc

        # Read output lines looking for the device URL and code
        output_lines = []
        device_url = None
        device_code = None
        import time
        deadline = time.time() + 30  # 30s timeout for initial output

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break  # Process exited
                continue
            output_lines.append(line.strip())
            full_output = " ".join(output_lines)

            # Look for GitHub device flow URL and code
            url_match = re.search(r'(https://github\.com/login/device)', full_output)
            if url_match:
                device_url = url_match.group(1)

            code_match = re.search(r'code\s+([A-Z0-9]{4}-[A-Z0-9]{4})', full_output, re.IGNORECASE)
            if code_match:
                device_code = code_match.group(1)

            # If we have both, return immediately (process keeps running)
            if device_url and device_code:
                return {
                    "status": "waiting_for_browser",
                    "device_url": device_url,
                    "device_code": device_code,
                    "message": f"Open {device_url} and enter code {device_code}",
                }

        # Process may have exited successfully (already authed)
        if proc.poll() is not None and proc.returncode == 0:
            if container_name in _auth_processes:
                del _auth_processes[container_name]
            return {"status": "already_authenticated"}

        # Timeout or couldn't parse
        if container_name in _auth_processes:
            try:
                proc.kill()
            except Exception:
                pass
            del _auth_processes[container_name]
        return {
            "status": "error",
            "message": "Could not get device code. Output: " + "\n".join(output_lines[-5:]),
        }

    try:
        return await asyncio.to_thread(_start_auth)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tunnel/auth/status")
async def tunnel_auth_status(container_name: str) -> dict:
    """Check if a pending tunnel auth has completed."""
    proc = _auth_processes.get(container_name)
    if proc is None:
        return {"status": "no_pending_auth"}

    poll = proc.poll()
    if poll is None:
        return {"status": "waiting_for_browser"}

    # Process finished
    del _auth_processes[container_name]
    if poll == 0:
        return {"status": "authenticated"}
    else:
        return {"status": "failed", "message": f"Auth process exited with code {poll}"}
