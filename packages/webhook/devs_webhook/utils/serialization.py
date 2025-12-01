"""JSON serialization utilities for webhook objects."""

import json
import base64
from typing import Any, Dict
from pathlib import Path
from datetime import datetime

from ..github.models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent
from devs_common.devs_config import DevsOptions


class WebhookEventEncoder(json.JSONEncoder):
    """Custom JSON encoder for WebhookEvent objects."""
    
    def default(self, obj):
        # Handle datetime objects
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle pydantic BaseModel instances
        elif hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif isinstance(obj, (IssueEvent, PullRequestEvent, CommentEvent)):
            return {
                '__type__': obj.__class__.__name__,
                '__data__': obj.model_dump()
            }
        elif isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


def serialize_webhook_event(event: WebhookEvent) -> str:
    """Serialize WebhookEvent to base64-encoded JSON string.
    
    Args:
        event: WebhookEvent to serialize
        
    Returns:
        Base64-encoded JSON string
    """
    json_str = json.dumps(event, cls=WebhookEventEncoder, ensure_ascii=True)
    return base64.b64encode(json_str.encode()).decode('ascii')


def deserialize_webhook_event(data: str) -> WebhookEvent:
    """Deserialize WebhookEvent from base64-encoded JSON string.
    
    Args:
        data: Base64-encoded JSON string
        
    Returns:
        WebhookEvent instance
    """
    json_str = base64.b64decode(data.encode('ascii')).decode()
    raw_data = json.loads(json_str)
    
    # Reconstruct the appropriate event type
    event_type = raw_data.get('__type__')
    event_data = raw_data.get('__data__', raw_data)
    
    if event_type == 'IssueEvent':
        return IssueEvent.model_validate(event_data)
    elif event_type == 'PullRequestEvent':
        return PullRequestEvent.model_validate(event_data)
    elif event_type == 'CommentEvent':
        return CommentEvent.model_validate(event_data)
    else:
        # Fallback - try to determine from data structure
        if 'issue' in event_data:
            return IssueEvent.model_validate(event_data)
        elif 'pull_request' in event_data:
            return PullRequestEvent.model_validate(event_data)
        else:
            return CommentEvent.model_validate(event_data)


def serialize_devs_options(options: DevsOptions) -> str:
    """Serialize DevsOptions to base64-encoded JSON string.
    
    Args:
        options: DevsOptions to serialize
        
    Returns:
        Base64-encoded JSON string
    """
    json_str = json.dumps(options.model_dump(), ensure_ascii=True)
    return base64.b64encode(json_str.encode()).decode('ascii')


def deserialize_devs_options(data: str) -> DevsOptions:
    """Deserialize DevsOptions from base64-encoded JSON string.
    
    Args:
        data: Base64-encoded JSON string
        
    Returns:
        DevsOptions instance
    """
    json_str = base64.b64decode(data.encode('ascii')).decode()
    raw_data = json.loads(json_str)
    
    return DevsOptions.model_validate(raw_data)