"""FastAPI webhook server."""

import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog
import uuid

from .config import get_config, WebhookConfig
from .core.webhook_handler import WebhookHandler
from .utils.logging import setup_logging

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


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature.
    
    Args:
        payload: Raw webhook payload
        signature: GitHub signature header
        secret: Webhook secret
        
    Returns:
        True if signature is valid
    """
    if not signature.startswith("sha256="):
        return False
    
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "devs-webhook"}


@app.get("/health")
async def health():
    """Detailed health check."""
    config = get_config()
    
    return {
        "status": "healthy",
        "service": "devs-webhook",
        "version": "0.1.0",
        "dev_mode": config.dev_mode,
        "config": {
            "mentioned_user": config.github_mentioned_user,
            "container_pool": config.container_pool,
            "webhook_path": config.webhook_path,
            "log_format": config.log_format,
        }
    }


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
    if not verify_webhook_signature(payload, signature, config.github_webhook_secret):
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
async def status():
    """Get current webhook handler status."""
    return await get_webhook_handler().get_status()


@app.post("/container/{container_name}/stop")
async def stop_container(container_name: str):
    """Manually stop a container."""
    success = await get_webhook_handler().stop_container(container_name)
    if success:
        return {"status": "stopped", "container": container_name}
    else:
        raise HTTPException(status_code=404, detail="Container not found or failed to stop")


@app.get("/containers")
async def list_containers():
    """List all managed containers."""
    return await get_webhook_handler().list_containers()


@app.post("/testevent")
async def test_event(
    request: TestEventRequest,
    config: WebhookConfig = Depends(require_dev_mode)
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
    from .github.models import Repository, User, Issue, IssueEvent
    
    # Mock repository
    mock_repo = Repository(
        id=999999,
        name=request.repo.split("/")[-1],
        full_name=request.repo,
        owner=User(
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
    mock_issue = Issue(
        id=999999,
        number=999,
        title="Test Issue",
        body=f"Test prompt: {request.prompt}",
        state="open",
        user=User(
            login="test-user",
            id=999999,
            avatar_url="https://github.com/test.png",
            html_url="https://github.com/test-user"
        ),
        html_url=f"https://github.com/{request.repo}/issues/999",
        created_at="2023-01-01T00:00:00Z",
        updated_at="2023-01-01T00:00:00Z"
    )
    
    # Mock issue event
    mock_event = IssueEvent(
        action="opened",
        issue=mock_issue,
        repository=mock_repo,
        sender=mock_issue.user
    )
    
    # Generate workspace name for this test task
    repo_slug = request.repo.replace("/", "-")
    workspace_name = f"{repo_slug}-{delivery_id}"
    
    # Queue the task directly in the container pool
    success = await get_webhook_handler().container_pool.queue_task(
        task_id=delivery_id,
        repo_name=request.repo,
        task_description=request.prompt,
        event=mock_event,
        workspace_name=workspace_name
    )
    
    if success:
        logger.info("Test task queued successfully",
                   delivery_id=delivery_id,
                   repo=request.repo,
                   workspace=workspace_name)
        
        return JSONResponse(
            status_code=202,
            content={
                "status": "test_accepted",
                "delivery_id": delivery_id,
                "repo": request.repo,
                "prompt": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
                "workspace": workspace_name,
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