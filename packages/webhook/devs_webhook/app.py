"""FastAPI webhook server.

This module provides the FastAPI application for receiving GitHub webhooks.
It's part of the webhook task source and delegates processing to WebhookHandler,
which in turn uses TaskProcessor for the core business logic.

Architecture:
    FastAPI endpoints -> WebhookHandler -> TaskProcessor -> ContainerPool
"""

import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
import structlog
import uuid
from datetime import datetime, timezone

from .config import get_config, WebhookConfig
from .core.webhook_handler import WebhookHandler
from .utils.logging import setup_logging
from .utils.github import verify_github_signature

# Set up logging
setup_logging()
logger = structlog.get_logger()


class TestEventRequest(BaseModel):
    """Request model for test event endpoint."""
    prompt: str
    repo: str = "test/repo"  # Default test repository


class TestRunTestsRequest(BaseModel):
    """Request model for test runtests endpoint."""
    repo: str  # Repository name (org/repo format)
    branch: str = "main"  # Branch to test
    commit_sha: str = "HEAD"  # Commit SHA to test
    pr_number: Optional[int] = None  # PR number (creates PR event instead of push event)


# Initialize webhook handler lazily (used in lifespan)
webhook_handler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events (startup and shutdown)."""
    # Startup: nothing needed currently
    yield
    # Shutdown: clean up all running containers
    global webhook_handler
    if webhook_handler is not None:
        logger.info("Graceful shutdown initiated - cleaning up containers")
        try:
            await webhook_handler.container_pool.shutdown()
            logger.info("Graceful shutdown complete - all containers cleaned up")
        except Exception as e:
            logger.error("Error during graceful shutdown", error=str(e))


# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="DevContainer Webhook Handler",
    description="GitHub webhook handler for automated devcontainer operations with Claude Code",
    version="0.1.0",
    lifespan=lifespan
)

# Security setup for admin endpoints
security = HTTPBasic()


def get_webhook_handler():
    """Get or create the webhook handler."""
    global webhook_handler
    if webhook_handler is None:
        webhook_handler = WebhookHandler()
    return webhook_handler


def require_dev_mode(config: WebhookConfig = Depends(get_config)):
    """Dependency that requires development mode."""
    if not config.dev_mode:
        raise HTTPException(
            status_code=404, 
            detail="This endpoint is only available in development mode"
        )


def verify_admin_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
    config: WebhookConfig = Depends(get_config)
):
    """Verify admin credentials for protected endpoints.
    
    Args:
        credentials: HTTP Basic auth credentials
        config: Webhook configuration
        
    Returns:
        Username if authentication successful
        
    Raises:
        HTTPException: If authentication fails
    """
    # In dev mode with no password set, allow any credentials
    if config.dev_mode and not config.admin_password:
        logger.warning("Admin auth bypassed in dev mode without password")
        return credentials.username
    
    # Verify username and password
    correct_username = secrets.compare_digest(
        credentials.username, config.admin_username
    )
    correct_password = secrets.compare_digest(
        credentials.password, config.admin_password
    )
    
    if not (correct_username and correct_password):
        logger.warning(
            "Failed admin authentication attempt",
            username=credentials.username
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    return credentials.username


# verify_github_signature is now imported from .utils module


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "devs-webhook"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "devs-webhook"}


@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events."""
    config = get_config()
    
    # Get headers
    headers = dict(request.headers)
    
    # Read payload
    payload = await request.body()
    
    # Verify signature
    signature = headers.get("x-hub-signature-256", "")
    if not verify_github_signature(payload, signature, config.github_webhook_secret):
        logger.warning("Invalid webhook signature", signature=signature)
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Get event type
    event_type = headers.get("x-github-event", "unknown")
    delivery_id = headers.get("x-github-delivery", "unknown")
    
    logger.info(
        "Webhook received",
        event_type=event_type,
        delivery_id=delivery_id,
        payload_size=len(payload)
    )
    
    # Process webhook in background
    background_tasks.add_task(
        get_webhook_handler().process_webhook,
        headers,
        payload,
        delivery_id
    )
    
    return JSONResponse(
        status_code=200,
        content={"status": "accepted", "delivery_id": delivery_id}
    )


@app.get("/status")
async def get_status(username: str = Depends(verify_admin_credentials)):
    """Get current webhook handler status.
    
    Requires admin authentication.
    """
    logger.info("Status endpoint accessed", authenticated_user=username)
    return await get_webhook_handler().get_status()


@app.post("/container/{container_name}/stop")
async def stop_container(
    container_name: str,
    username: str = Depends(verify_admin_credentials)
):
    """Manually stop a container.
    
    Requires admin authentication.
    """
    logger.info(
        "Container stop requested",
        container=container_name,
        authenticated_user=username
    )
    success = await get_webhook_handler().stop_container(container_name)
    if success:
        return {"status": "stopped", "container": container_name}
    else:
        raise HTTPException(status_code=404, detail="Container not found or failed to stop")


@app.get("/containers")
async def list_containers(username: str = Depends(verify_admin_credentials)):
    """List all managed containers.
    
    Requires admin authentication.
    """
    logger.info("Containers list accessed", authenticated_user=username)
    return await get_webhook_handler().list_containers()


@app.post("/testevent")
async def test_event(
    request: TestEventRequest,
    config: WebhookConfig = Depends(require_dev_mode),
    username: str = Depends(verify_admin_credentials)
):
    """Test endpoint to simulate GitHub webhook events with custom prompts.
    
    Only available in development mode.
    
    Example:
        POST /testevent
        {
            "prompt": "Fix the login bug in the authentication module",
            "repo": "myorg/myproject"
        }
    """
    # Generate a unique delivery ID for this test
    delivery_id = f"test-{uuid.uuid4().hex[:8]}"
    
    logger.info(
        "Test event received",
        prompt_length=len(request.prompt),
        repo=request.repo,
        delivery_id=delivery_id
    )
    
    # Create a minimal mock webhook event
    from .github.models import GitHubRepository, GitHubUser, GitHubIssue, TestIssueEvent
    
    # Mock repository
    mock_repo = GitHubRepository(
        id=999999,
        name=request.repo.split("/")[-1],
        full_name=request.repo,
        owner=GitHubUser(
            login=request.repo.split("/")[0],
            id=999999,
            avatar_url="https://github.com/test.png",
            html_url=f"https://github.com/{request.repo.split('/')[0]}"
        ),
        html_url=f"https://github.com/{request.repo}",
        clone_url=f"https://github.com/{request.repo}.git",
        ssh_url=f"git@github.com:{request.repo}.git",
        default_branch="main"
    )
    
    # Mock issue with the prompt
    mock_issue = GitHubIssue(
        id=999999,
        number=999,
        title="Test Issue",
        body=f"Test prompt: {request.prompt}",
        state="open",
        user=GitHubUser(
            login="test-user",
            id=999999,
            avatar_url="https://github.com/test.png",
            html_url="https://github.com/test-user"
        ),
        html_url=f"https://github.com/{request.repo}/issues/999",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc)
    )
    
    # Mock issue event
    mock_event = TestIssueEvent(
        action="opened",
        issue=mock_issue,
        repository=mock_repo,
        sender=mock_issue.user
    )
    
    # Queue the task directly in the container pool
    success = await get_webhook_handler().container_pool.queue_task(
        task_id=delivery_id,
        repo_name=request.repo,
        task_description=request.prompt,
        event=mock_event,
    )
    
    if success:
        logger.info("Test task queued successfully",
                   delivery_id=delivery_id,
                   repo=request.repo)

        return JSONResponse(
            status_code=202,
            content={
                "status": "test_accepted",
                "delivery_id": delivery_id,
                "repo": request.repo,
                "prompt": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
                "message": "Test task queued for processing"
            }
        )
    else:
        logger.error("Failed to queue test task",
                    delivery_id=delivery_id,
                    repo=request.repo)

        raise HTTPException(
            status_code=500,
            detail="Failed to queue test task"
        )


@app.post("/testruntests")
async def test_runtests(
    request: TestRunTestsRequest,
    config: WebhookConfig = Depends(require_dev_mode),
    username: str = Depends(verify_admin_credentials)
):
    """Test endpoint to simulate GitHub push or PR events for CI/runtests testing.

    Only available in development mode. Skips GitHub Checks API calls.

    Example (push event):
        POST /testruntests
        {
            "repo": "myorg/myproject",
            "branch": "main",
            "commit_sha": "abc123"
        }

    Example (PR event):
        POST /testruntests
        {
            "repo": "myorg/myproject",
            "branch": "feature-branch",
            "commit_sha": "abc123",
            "pr_number": 42
        }
    """
    # Generate a unique delivery ID for this test
    delivery_id = f"test-ci-{uuid.uuid4().hex[:8]}"

    logger.info(
        "Test runtests event received",
        repo=request.repo,
        branch=request.branch,
        commit_sha=request.commit_sha,
        pr_number=request.pr_number,
        delivery_id=delivery_id
    )

    from .github.models import GitHubRepository, GitHubUser, GitHubPullRequest, TestPushEvent, TestPullRequestEvent

    # Mock repository
    mock_repo = GitHubRepository(
        id=999999,
        name=request.repo.split("/")[-1],
        full_name=request.repo,
        owner=GitHubUser(
            login=request.repo.split("/")[0],
            id=999999,
            avatar_url="https://github.com/test.png",
            html_url=f"https://github.com/{request.repo.split('/')[0]}"
        ),
        html_url=f"https://github.com/{request.repo}",
        clone_url=f"https://github.com/{request.repo}.git",
        ssh_url=f"git@github.com:{request.repo}.git",
        default_branch="main"
    )

    mock_user = GitHubUser(
        login="test-user",
        id=999999,
        avatar_url="https://github.com/test.png",
        html_url="https://github.com/test-user"
    )

    # Create PR event if pr_number is provided, otherwise push event
    if request.pr_number is not None:
        # Mock PR event - this will trigger the PR branch fetch logic
        mock_pr = GitHubPullRequest(
            id=999999,
            number=request.pr_number,
            title=f"Test PR #{request.pr_number}",
            body="Test PR for CI testing",
            state="open",
            user=mock_user,
            html_url=f"https://github.com/{request.repo}/pull/{request.pr_number}",
            head={
                "ref": request.branch,
                "sha": request.commit_sha if request.commit_sha != "HEAD" else "test-sha",
                "label": f"{request.repo.split('/')[0]}:{request.branch}",
                "user": {"login": request.repo.split("/")[0]},
                "repo": {"full_name": request.repo}
            },
            base={
                "ref": "main",
                "sha": "base-sha",
                "label": f"{request.repo.split('/')[0]}:main"
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        mock_event = TestPullRequestEvent(
            action="synchronize",
            repository=mock_repo,
            sender=mock_user,
            pull_request=mock_pr
        )
        event_type = "PR"
    else:
        # Mock push event
        mock_event = TestPushEvent(
            action="pushed",
            repository=mock_repo,
            sender=mock_user,
            ref=f"refs/heads/{request.branch}",
            before="0000000000000000000000000000000000000000",
            # Use branch name when HEAD is specified - git checkout works with branch names
            after=request.commit_sha if request.commit_sha != "HEAD" else request.branch,
            created=False,
            deleted=False,
            forced=False,
            compare=f"https://github.com/{request.repo}/compare/main...{request.branch}",
            commits=[],
            head_commit={
                "id": request.commit_sha if request.commit_sha != "HEAD" else request.branch,
                "message": "Test commit for CI",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": f"https://github.com/{request.repo}/commit/{request.commit_sha}",
                "author": {"name": "Test User", "email": "test@example.com"},
                "committer": {"name": "Test User", "email": "test@example.com"},
                "added": [],
                "removed": [],
                "modified": []
            }
        )
        event_type = "push"

    # Queue the task directly in the container pool as a CI task
    success = await get_webhook_handler().container_pool.queue_task(
        task_id=delivery_id,
        repo_name=request.repo,
        task_description=None,  # CI tasks don't have a description
        event=mock_event,
        task_type='tests'  # Use TestDispatcher for CI tasks
    )

    if success:
        logger.info("Test CI task queued successfully",
                   delivery_id=delivery_id,
                   repo=request.repo,
                   branch=request.branch,
                   event_type=event_type)

        response_content = {
            "status": "test_ci_accepted",
            "delivery_id": delivery_id,
            "repo": request.repo,
            "branch": request.branch,
            "commit_sha": request.commit_sha,
            "event_type": event_type,
            "message": f"Test CI task ({event_type} event) queued for processing (GitHub Checks API calls will be skipped)"
        }
        if request.pr_number is not None:
            response_content["pr_number"] = request.pr_number

        return JSONResponse(
            status_code=202,
            content=response_content
        )
    else:
        logger.error("Failed to queue test CI task",
                    delivery_id=delivery_id,
                    repo=request.repo)

        raise HTTPException(
            status_code=500,
            detail="Failed to queue test CI task"
        )


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )