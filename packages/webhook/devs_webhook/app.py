"""FastAPI webhook server.

This module provides the FastAPI application for receiving GitHub webhooks.
It's part of the webhook task source and delegates processing to WebhookHandler,
which in turn uses TaskProcessor for the core business logic.

Architecture:
    FastAPI endpoints -> WebhookHandler -> TaskProcessor -> ContainerPool
"""

import secrets
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
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

# Initialize FastAPI app
app = FastAPI(
    title="DevContainer Webhook Handler",
    description="GitHub webhook handler for automated devcontainer operations with Claude Code",
    version="0.1.0"
)

# Security setup for admin endpoints
security = HTTPBasic()

# Initialize webhook handler lazily
webhook_handler = None


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


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )