"""API routes for webadmin."""

import asyncio
import re
import subprocess
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

from devs_common.core.container import (
    ContainerManager,
    make_tunnel_name,
    get_container_workspace_dir,
    kill_tunnel_processes,
)
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


class TunnelRequest(BaseModel):
    project_name: str  # org-repo format (from container list)
    dev_name: str


def _get_repo_project(repo: str) -> Project:
    """Clone/update a repo via cache and return a Project for it."""
    repo_cache = RepoCache(cache_dir=config.repo_cache_dir)
    repo_path = repo_cache.ensure_repo(repo)
    return Project(project_dir=repo_path)


def _get_container_name(project_name: str, dev_name: str) -> str:
    """Derive container name from project_name + dev_name."""
    project_prefix = config.project_prefix if config else "dev"
    return f"{project_prefix}-{project_name}-{dev_name}"


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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error starting container", repo=request.repo, dev_name=request.dev_name)
        raise HTTPException(status_code=500, detail=str(e))


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

def _docker_exec(container_name: str, cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a docker exec command."""
    full_cmd = ["docker", "exec", container_name] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)


def _tunnel_info(project_name: str, dev_name: str) -> dict:
    """Derive all tunnel-related names/paths from project_name + dev_name."""
    container_name = _get_container_name(project_name, dev_name)
    tunnel_name = make_tunnel_name(container_name)
    workspace_dir = get_container_workspace_dir(container_name)
    return {
        "container_name": container_name,
        "tunnel_name": tunnel_name,
        "workspace_dir": workspace_dir,
        "web_url": f"https://vscode.dev/tunnel/{tunnel_name}{workspace_dir}",
        "vscode_cmd": f"code --remote tunnel+{tunnel_name} {workspace_dir}",
    }


# --- Tunnel endpoints ---

@router.get("/tunnel/status")
async def tunnel_status(project_name: str, dev_name: str) -> dict:
    """Get VS Code tunnel status for a container."""
    info = _tunnel_info(project_name, dev_name)
    try:
        result = await asyncio.to_thread(
            _docker_exec, info["container_name"],
            ["/usr/local/bin/code", "tunnel", "status"]
        )

        import json
        raw_status = {}
        if result.returncode == 0:
            try:
                raw_status = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                pass

        tunnel_data = raw_status.get("tunnel") or {}
        is_connected = tunnel_data.get("tunnel") == "Connected"

        return {
            "running": is_connected,
            "tunnel_name": info["tunnel_name"],
            "web_url": info["web_url"] if is_connected else None,
            "vscode_cmd": info["vscode_cmd"] if is_connected else None,
        }
    except subprocess.TimeoutExpired:
        return {"running": False, "message": "Status check timed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/start")
async def tunnel_start(request: TunnelRequest) -> dict:
    """Start a VS Code tunnel in a container (background)."""
    info = _tunnel_info(request.project_name, request.dev_name)
    container_name = info["container_name"]
    tunnel_name = info["tunnel_name"]
    log_file = "/tmp/vscode-tunnel.log"
    tunnel_cmd = f"/usr/local/bin/code tunnel --accept-server-license-terms --name {tunnel_name}"

    def _start() -> dict:
        # Kill any stale tunnel processes and clear log before starting
        kill_tunnel_processes(container_name)
        subprocess.run(
            ["docker", "exec", container_name, "/bin/sh", "-c", f"> {log_file}"],
            capture_output=True,
        )
        time.sleep(1)

        # Start tunnel in background
        subprocess.run(
            ["docker", "exec", "-d", container_name,
             "/bin/sh", "-c", f"{tunnel_cmd} > {log_file} 2>&1"],
            check=True,
        )

        # Poll for startup (up to 15s)
        for _ in range(15):
            time.sleep(1)
            result = subprocess.run(
                ["docker", "exec", container_name, "cat", log_file],
                capture_output=True, text=True,
            )
            output = result.stdout

            if "Open this link" in output or "vscode.dev/tunnel" in output:
                return {
                    "status": "running",
                    "tunnel_name": info["tunnel_name"],
                    "web_url": info["web_url"],
                    "vscode_cmd": info["vscode_cmd"],
                }

            if "log in" in output.lower() or "device" in output.lower() or "invalid" in output.lower():
                kill_tunnel_processes(container_name)
                return {"status": "auth_required", "tunnel_name": info["tunnel_name"]}

        return {
            "status": "starting",
            "tunnel_name": info["tunnel_name"],
            "message": "Tunnel may still be starting, check status",
        }

    try:
        return await asyncio.to_thread(_start)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/kill")
async def tunnel_kill(request: TunnelRequest) -> dict:
    """Kill a running VS Code tunnel."""
    info = _tunnel_info(request.project_name, request.dev_name)
    try:
        await asyncio.to_thread(kill_tunnel_processes, info["container_name"])
        return {"killed": True, "message": "Tunnel processes killed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/auth")
async def tunnel_auth_start(request: TunnelRequest) -> dict:
    """Start tunnel auth (GitHub device flow).

    Launches the login command, captures the device URL + code,
    and returns them so the user can complete auth in their browser.
    The process keeps running until auth completes or is cancelled.
    """
    info = _tunnel_info(request.project_name, request.dev_name)
    container_name = info["container_name"]

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
        deadline = time.time() + 30

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            output_lines.append(line.strip())
            full_output = " ".join(output_lines)

            url_match = re.search(r'(https://github\.com/login/device)', full_output)
            if url_match:
                device_url = url_match.group(1)

            code_match = re.search(r'code\s+([A-Z0-9]{4}-[A-Z0-9]{4})', full_output, re.IGNORECASE)
            if code_match:
                device_code = code_match.group(1)

            if device_url and device_code:
                return {
                    "status": "waiting_for_browser",
                    "device_url": device_url,
                    "device_code": device_code,
                    "message": f"Open {device_url} and enter code {device_code}",
                }

        if proc.poll() is not None and proc.returncode == 0:
            if container_name in _auth_processes:
                del _auth_processes[container_name]
            return {"status": "already_authenticated"}

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
async def tunnel_auth_status(project_name: str, dev_name: str) -> dict:
    """Check if a pending tunnel auth has completed."""
    info = _tunnel_info(project_name, dev_name)
    container_name = info["container_name"]

    proc = _auth_processes.get(container_name)
    if proc is None:
        return {"status": "no_pending_auth"}

    poll = proc.poll()
    if poll is None:
        return {"status": "waiting_for_browser"}

    del _auth_processes[container_name]
    if poll == 0:
        return {"status": "authenticated"}
    else:
        return {"status": "failed", "message": f"Auth process exited with code {poll}"}
