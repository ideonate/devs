"""API routes for webadmin."""

import asyncio
import contextvars
import functools
import json
import re
import subprocess
import threading
from typing import Any, Callable, Dict, Optional, TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

from devs_common.core.container import ContainerManager, make_tunnel_name
from devs_common.core.workspace import WorkspaceManager
from devs_common.core.project import Project
from devs_common.utils.repo_cache import RepoCache
from devs_common.utils.docker_client import DockerClient
from devs_common.devs_config import DevsConfigLoader
from devs_common.exceptions import DevsError

from ..config import config
from .tunnel_exec import TunnelExec, container_workspace_dir, run_tunnel_exec

logger = structlog.get_logger()

router = APIRouter(prefix="/api")

_TUNNEL_CLI = "/usr/local/bin/code"
_TUNNEL_LOG = "/tmp/vscode-tunnel.log"
# Matches every way devs launches the tunnel (webadmin, CLI, start-tunnel.sh).
_TUNNEL_PATTERN = "code tunnel --accept-server-license-terms"
# How long Start waits for the new tunnel to connect or ask for a device login.
_START_GRACE_SECONDS = 8.0
# How long sign-in waits for the GitHub device code.
_AUTH_TIMEOUT_SECONDS = 30.0
_auth_processes: Dict[str, TunnelExec] = {}
_auth_locks: Dict[str, threading.Lock] = {}
_auth_locks_guard = threading.Lock()

_T = TypeVar("_T")


async def _to_thread(func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    """Equivalent of asyncio.to_thread (added in Python 3.9)."""
    loop = asyncio.get_running_loop()
    call = functools.partial(contextvars.copy_context().run, func, *args, **kwargs)
    return await loop.run_in_executor(None, call)


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
            project = await _to_thread(_get_repo_project, repo)
            container_manager = ContainerManager(project, config)
            containers = await _to_thread(container_manager.list_containers)
        else:
            containers = await _to_thread(ContainerManager.list_all_containers)

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
        project = await _to_thread(_get_repo_project, request.repo)
        container_manager = ContainerManager(project, config)
        workspace_manager = WorkspaceManager(project, config)

        devs_env = DevsConfigLoader.load_env_vars(request.dev_name, project.info.name)
        extra_env = devs_env if devs_env else None

        workspace_dir = await _to_thread(
            workspace_manager.create_workspace, request.dev_name
        )

        success = await _to_thread(
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

    success = await _to_thread(_restart, request.container_name)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Container {request.container_name} not found or cannot be started",
        )

    return {"status": "started", "container_name": request.container_name}


@router.post("/stop")
async def stop_container(request: ContainerActionRequest) -> dict:
    """Stop a container by Docker name (preserves state)."""
    success = await _to_thread(_stop_by_name, request.container_name, False)

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
    await _to_thread(_stop_by_name, request.container_name, True)

    # Clean workspace if we found the labels
    if dev_name and project_name:
        await _to_thread(_clean_workspace, project_name, dev_name)

    return {"status": "cleaned", "container_name": request.container_name}


# --- Tunnel helpers ---

def _tunnel_error(returncode: int, output: str) -> str:
    if returncode == 127:
        return f"Install the standalone VS Code CLI at {_TUNNEL_CLI} in the devcontainer."
    return output.strip() or f"VS Code CLI exited with status {returncode}."


def _tunnel_state(container_name: str) -> Optional[dict]:
    """Return the tunnel's status entry, or None when no tunnel process exists."""
    result = run_tunnel_exec(container_name, [_TUNNEL_CLI, "tunnel", "status"])
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.splitlines()):
        try:
            status = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(status, dict) and "tunnel" in status:
            tunnel = status["tunnel"]
            return tunnel if isinstance(tunnel, dict) else None
    return None


def _workspace_dir(container_name: str, default: str) -> str:
    """The folder to open over the tunnel: the container's real workspace mount."""
    try:
        return container_workspace_dir(container_name) or default
    except Exception:
        return default


def _kill_tunnel(container_name: str) -> None:
    """Stop the tunnel, whether or not the CLI singleton still answers."""
    try:
        result = run_tunnel_exec(container_name, [_TUNNEL_CLI, "tunnel", "kill"])
    except subprocess.TimeoutExpired:
        result = None
    if result is not None and result.returncode == 127:
        raise HTTPException(status_code=400, detail=_tunnel_error(127, result.stdout))
    # `code tunnel kill` fails when nothing is running, and can't reach a tunnel
    # whose singleton is wedged; pkill covers both (exit 1 = nothing matched).
    run_tunnel_exec(container_name, ["pkill", "-f", _TUNNEL_PATTERN])


def _device_login(output: str) -> Optional[dict]:
    url = re.search(r"https://github\.com/login/device", output)
    code = re.search(r"code\s+([A-Z0-9]{4}-[A-Z0-9]{4})", output, re.IGNORECASE)
    if not (url and code):
        return None
    device_url, device_code = url.group(), code.group(1)
    return {
        "device_url": device_url,
        "device_code": device_code,
        "message": f"Open {device_url} and enter code {device_code}",
    }


def _auth_lock(container_name: str) -> threading.Lock:
    with _auth_locks_guard:
        return _auth_locks.setdefault(container_name, threading.Lock())


# --- Tunnel endpoints ---

@router.get("/tunnel/status")
async def tunnel_status(project_name: str, dev_name: str) -> dict:
    """Get VS Code tunnel status for a container."""
    container_name = _get_container_name(project_name, dev_name)

    def _status() -> dict:
        tunnel = _tunnel_state(container_name) or {}
        # Use the actual tunnel name from status if available
        tunnel_name = tunnel.get("name") or make_tunnel_name(container_name)
        if tunnel.get("tunnel") != "Connected":
            return {"running": False, "tunnel_name": tunnel_name,
                    "web_url": None, "vscode_cmd": None}
        workspace_dir = _workspace_dir(
            container_name, f"/workspaces/{project_name}-{dev_name}"
        )
        return {
            "running": True,
            "tunnel_name": tunnel_name,
            "web_url": f"https://vscode.dev/tunnel/{tunnel_name}{workspace_dir}",
            "vscode_cmd": f"code --remote tunnel+{tunnel_name} {workspace_dir}",
        }

    try:
        return await _to_thread(_status)
    except subprocess.TimeoutExpired:
        return {"running": False, "message": "Status check timed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/start")
async def tunnel_start(request: TunnelRequest) -> dict:
    """Start a VS Code tunnel in a container (background).

    Returns {"status": "starting"} once the tunnel is launched; the caller should
    poll GET /api/tunnel/status until running==true. If the tunnel's stored
    credentials no longer work, it asks for a GitHub device login, and this
    returns {"status": "waiting_for_browser", device_url, device_code}; the
    tunnel connects by itself once the user completes it.
    """
    container_name = _get_container_name(request.project_name, request.dev_name)
    tunnel_name = make_tunnel_name(container_name)

    def _start() -> dict:
        result = run_tunnel_exec(
            container_name, [_TUNNEL_CLI, "tunnel", "user", "show"]
        )
        if result.returncode == 1 and "not logged in" in result.stdout.lower():
            return {"status": "auth_required", "tunnel_name": tunnel_name}
        if result.returncode != 0:
            raise HTTPException(
                status_code=400, detail=_tunnel_error(result.returncode, result.stdout)
            )

        existing = _tunnel_state(container_name)
        if existing is not None:
            if existing.get("tunnel") == "Connected":
                return {"status": "running", "tunnel_name": existing.get("name") or tunnel_name}
            # A new `code tunnel` would only attach to this one and ignore --name.
            _kill_tunnel(container_name)

        launch = TunnelExec(
            container_name,
            [_TUNNEL_CLI, "tunnel", "--accept-server-license-terms", "--name", tunnel_name],
            output_path=_TUNNEL_LOG,
        )
        try:
            returncode, log = launch.wait(
                _START_GRACE_SECONDS, 0.5,
                until=lambda log: _device_login(log) or "vscode.dev/tunnel" in log,
            )
        finally:
            launch.release()
        device = _device_login(log)
        if device:
            return {"status": "waiting_for_browser", "tunnel_name": tunnel_name, **device}
        if returncode is not None:
            raise HTTPException(status_code=400, detail=_tunnel_error(returncode, log))
        return {"status": "starting", "tunnel_name": tunnel_name}

    try:
        return await _to_thread(_start)
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tunnel startup timed out.") from None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/kill")
async def tunnel_kill(request: TunnelRequest) -> dict:
    """Kill the VS Code tunnel; succeeds when none is running."""
    container_name = _get_container_name(request.project_name, request.dev_name)
    try:
        await _to_thread(_kill_tunnel, container_name)
        return {"killed": True, "message": "Tunnel processes killed"}
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tunnel shutdown timed out.") from None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/auth")
async def tunnel_auth_start(request: TunnelRequest) -> dict:
    """Start tunnel auth (GitHub device flow).

    Launches the login command, captures the device URL + code,
    and returns them so the user can complete auth in their browser.
    The process keeps running until auth completes or is cancelled.
    A repeated request reuses the pending login instead of starting another.
    """
    container_name = _get_container_name(request.project_name, request.dev_name)

    def _start_auth() -> dict:
        # Serialise per container, so overlapping requests share one login.
        with _auth_lock(container_name):
            execution = _auth_processes.pop(container_name, None)
            if execution is None:
                execution = TunnelExec(
                    container_name,
                    [_TUNNEL_CLI, "tunnel", "user", "login", "--provider", "github"],
                )
            try:
                returncode, output = execution.wait(
                    _AUTH_TIMEOUT_SECONDS, 0.5, until=_device_login
                )
            except BaseException:
                execution.close()
                raise
            device = _device_login(output)
            if returncode is None and device:
                _auth_processes[container_name] = execution
                return {"status": "waiting_for_browser", **device}
            execution.close()
        if returncode == 0:
            return {"status": "already_authenticated"}
        if returncode is not None:
            return {
                "status": "error",
                "message": "Could not get device code. " + output.strip(),
            }
        raise subprocess.TimeoutExpired("VS Code GitHub sign-in", _AUTH_TIMEOUT_SECONDS)

    try:
        return await _to_thread(_start_auth)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="GitHub sign-in timed out.") from None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tunnel/auth/status")
async def tunnel_auth_status(project_name: str, dev_name: str) -> dict:
    """Check if a pending tunnel auth has completed."""
    container_name = _get_container_name(project_name, dev_name)

    execution = _auth_processes.get(container_name)
    if execution is None:
        return {"status": "no_pending_auth"}

    try:
        returncode = await _to_thread(execution.poll)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if returncode is None:
        return {"status": "waiting_for_browser"}

    if _auth_processes.get(container_name) is execution:
        del _auth_processes[container_name]
        await _to_thread(execution.close)
    if returncode == 0:
        return {"status": "authenticated"}
    else:
        return {"status": "failed", "message": f"Auth process exited with code {returncode}"}
