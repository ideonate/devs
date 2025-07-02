"""FastAPI webhook server."""

import hmac
import hashlib
from typing import Dict
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import structlog

from .config import get_config
from .core.webhook_handler import WebhookHandler
from .utils.logging import setup_logging

# Set up logging
setup_logging()
logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="DevContainer Webhook Handler",
    description="GitHub webhook handler for automated devcontainer operations with Claude Code",
    version="0.1.0"
)

# Initialize webhook handler
webhook_handler = WebhookHandler()


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
        "config": {
            "mentioned_user": config.mentioned_user,
            "container_pool": config.container_pool,
            "webhook_path": config.webhook_path,
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
    if not verify_webhook_signature(payload, signature, config.webhook_secret):
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
        webhook_handler.process_webhook,
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
    return await webhook_handler.get_status()


@app.post("/container/{container_name}/stop")
async def stop_container(container_name: str):
    """Manually stop a container."""
    success = await webhook_handler.stop_container(container_name)
    if success:
        return {"status": "stopped", "container": container_name}
    else:
        raise HTTPException(status_code=404, detail="Container not found or failed to stop")


@app.get("/containers")
async def list_containers():
    """List all managed containers."""
    return await webhook_handler.list_containers()


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )