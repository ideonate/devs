"""API routes for webadmin."""

import asyncio
from typing import Optional

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
