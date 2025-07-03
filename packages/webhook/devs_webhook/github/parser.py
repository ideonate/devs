"""GitHub webhook payload parsing."""

import json
from typing import Optional, Dict, Any
from .models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent


class WebhookParser:
    """Parses GitHub webhook payloads into structured events."""
    
    @staticmethod
    def parse_webhook(headers: Dict[str, str], payload: bytes) -> Optional[WebhookEvent]:
        """Parse a GitHub webhook payload into a structured event.
        
        Args:
            headers: HTTP headers from the webhook request
            payload: Raw webhook payload bytes
            
        Returns:
            Parsed webhook event or None if not supported/parseable
        """
        try:
            event_type = headers.get("x-github-event", "").lower()
            data = json.loads(payload.decode("utf-8"))
            
            if event_type == "issues":
                return WebhookParser._parse_issue_event(data)
            elif event_type == "pull_request":
                return WebhookParser._parse_pull_request_event(data)
            elif event_type == "issue_comment":
                return WebhookParser._parse_issue_comment_event(data)
            elif event_type == "pull_request_review_comment":
                return WebhookParser._parse_pr_comment_event(data)
            else:
                # Unsupported event type
                return None
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Invalid payload format
            return None
    
    @staticmethod
    def _parse_issue_event(data: Dict[str, Any]) -> IssueEvent:
        """Parse an issue webhook event."""
        return IssueEvent(**data)
    
    @staticmethod
    def _parse_pull_request_event(data: Dict[str, Any]) -> PullRequestEvent:
        """Parse a pull request webhook event."""
        return PullRequestEvent(**data)
    
    @staticmethod
    def _parse_issue_comment_event(data: Dict[str, Any]) -> CommentEvent:
        """Parse an issue comment webhook event."""
        return CommentEvent(
            action=data["action"],
            repository=data["repository"],
            sender=data["sender"],
            comment=data["comment"],
            issue=data.get("issue")  # Present for issue comments
        )
    
    @staticmethod
    def _parse_pr_comment_event(data: Dict[str, Any]) -> CommentEvent:
        """Parse a pull request comment webhook event."""
        return CommentEvent(
            action=data["action"],
            repository=data["repository"], 
            sender=data["sender"],
            comment=data["comment"],
            pull_request=data.get("pull_request")  # Present for PR comments
        )
    
    @staticmethod
    def should_process_event(event: WebhookEvent, mentioned_user: str) -> bool:
        """Check if an event should be processed based on @mentions.
        
        Args:
            event: Parsed webhook event
            mentioned_user: Username to look for in @mentions
            
        Returns:
            True if the event contains @mentions of the target user
        """
        # Process different types of relevant actions
        relevant_actions = ["opened", "created", "edited"]
        
        # For issues and PRs, also process assignments
        if isinstance(event, (IssueEvent, PullRequestEvent)):
            relevant_actions.append("assigned")
        
        if event.action not in relevant_actions:
            return False
        
        # Special handling for assignment events
        if event.action == "assigned":
            # Only process if the bot user was assigned
            assignee = None
            if isinstance(event, IssueEvent) and hasattr(event.issue, 'assignee'):
                assignee = event.issue.assignee
            elif isinstance(event, PullRequestEvent) and hasattr(event.pull_request, 'assignee'): 
                assignee = event.pull_request.assignee
            
            if assignee and assignee.login == mentioned_user:
                return True  # Bot was assigned, process it
            else:
                return False  # Someone else was assigned, ignore
        
        # Prevent feedback loops: Don't process events created by the bot user
        if event.sender.login == mentioned_user:
            return False
        
        # For comment events, also check if the comment author is the bot
        if isinstance(event, CommentEvent) and event.comment.user.login == mentioned_user:
            return False
        
        # Check for @mentions
        mentions = event.extract_mentions(mentioned_user)
        return len(mentions) > 0
    
