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
        import structlog
        logger = structlog.get_logger()
        
        logger.info("Checking if event should be processed",
                   event_type=type(event).__name__,
                   action=event.action,
                   mentioned_user=mentioned_user)
        
        # Process different types of relevant actions
        relevant_actions = ["opened", "created", "edited"]
        
        # For issues and PRs, also process assignments
        if isinstance(event, (IssueEvent, PullRequestEvent)):
            relevant_actions.append("assigned")
        
        logger.info("Relevant actions determined",
                   relevant_actions=relevant_actions,
                   event_action=event.action,
                   action_in_relevant=event.action in relevant_actions)
        
        if event.action not in relevant_actions:
            logger.info("Event action not in relevant actions, skipping",
                       action=event.action,
                       relevant_actions=relevant_actions)
            return False
        
        # Special handling for assignment events AND opened events with assignees
        if event.action == "assigned" or (event.action == "opened" and isinstance(event, (IssueEvent, PullRequestEvent))):
            logger.info("Checking for assignee",
                       event_type=type(event).__name__,
                       action=event.action)
            
            # Check if the bot user is assigned
            assignee = None
            if isinstance(event, IssueEvent):
                logger.info("Checking issue assignee",
                           has_issue=hasattr(event, 'issue'),
                           has_assignee=hasattr(event.issue, 'assignee') if hasattr(event, 'issue') else False)
                
                if hasattr(event.issue, 'assignee'):
                    assignee = event.issue.assignee
                    logger.info("Issue assignee found",
                               assignee_login=assignee.login if assignee else None,
                               assignee_is_none=assignee is None)
                    
            elif isinstance(event, PullRequestEvent):
                logger.info("Checking PR assignee",
                           has_pr=hasattr(event, 'pull_request'),
                           has_assignee=hasattr(event.pull_request, 'assignee') if hasattr(event, 'pull_request') else False)
                
                if hasattr(event.pull_request, 'assignee'):
                    assignee = event.pull_request.assignee
                    logger.info("PR assignee found",
                               assignee_login=assignee.login if assignee else None,
                               assignee_is_none=assignee is None)
            
            assignee_matches = assignee and assignee.login == mentioned_user
            logger.info("Assignment check result",
                       assignee_login=assignee.login if assignee else None,
                       mentioned_user=mentioned_user,
                       assignee_matches=assignee_matches)
            
            if assignee_matches:
                logger.info("Bot is assigned, processing event")
                return True  # Bot is assigned, process it
            elif event.action == "assigned":
                # For "assigned" action, only process if bot was assigned
                logger.info("Bot was not assigned in 'assigned' event, skipping")
                return False
            # For "opened" action, continue to check for mentions
        
        # Prevent feedback loops: Don't process events created by the bot user
        if event.sender.login == mentioned_user:
            logger.info("Event created by bot user, skipping to prevent feedback loop")
            return False
        
        # For comment events, also check if the comment author is the bot
        if isinstance(event, CommentEvent) and event.comment.user.login == mentioned_user:
            logger.info("Comment created by bot user, skipping to prevent feedback loop")
            return False
        
        # Check for @mentions
        mentions = event.extract_mentions(mentioned_user)
        logger.info("Checking for mentions",
                   mentions_found=len(mentions),
                   should_process=len(mentions) > 0)
        
        return len(mentions) > 0
    
