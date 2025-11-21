"""GitHub webhook payload parsing."""

import json
from typing import Optional, Dict, Any
from .models import WebhookEvent, IssueEvent, PullRequestEvent, CommentEvent, PushEvent


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
            elif event_type == "push":
                return WebhookParser._parse_push_event(data)
            else:
                # Unsupported event type
                return None
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Invalid payload format
            import structlog
            logger = structlog.get_logger()
            logger.error("Failed to parse webhook payload",
                        event_type=event_type,
                        error=str(e),
                        exc_info=True)
            return None
    
    @staticmethod
    def _parse_issue_event(data: Dict[str, Any]) -> IssueEvent:
        """Parse an issue webhook event."""
        # Ensure installation data is included if present
        return IssueEvent(**data)
    
    @staticmethod
    def _parse_pull_request_event(data: Dict[str, Any]) -> PullRequestEvent:
        """Parse a pull request webhook event."""
        # Ensure installation data is included if present
        return PullRequestEvent(**data)
    
    @staticmethod
    def _parse_issue_comment_event(data: Dict[str, Any]) -> CommentEvent:
        """Parse an issue comment webhook event."""
        issue_data = data.get("issue")
        
        # Always treat as issue - we'll detect PR nature in the processing logic
        return CommentEvent(
            action=data["action"],
            repository=data["repository"],
            sender=data["sender"],
            comment=data["comment"],
            issue=issue_data,  # Keep as issue, detect PR in logic
            installation=data.get("installation")  # Include installation if present
        )
    
    @staticmethod
    def _parse_pr_comment_event(data: Dict[str, Any]) -> CommentEvent:
        """Parse a pull request comment webhook event."""
        return CommentEvent(
            action=data["action"],
            repository=data["repository"], 
            sender=data["sender"],
            comment=data["comment"],
            pull_request=data.get("pull_request"),  # Present for PR comments
            installation=data.get("installation")  # Include installation if present
        )
    
    @staticmethod
    def _parse_push_event(data: Dict[str, Any]) -> PushEvent:
        """Parse a push webhook event."""
        return PushEvent(
            action="pushed",  # Push events don't have an action field, so we set a default
            repository=data["repository"],
            sender=data["sender"],
            installation=data.get("installation"),  # Include installation if present
            ref=data["ref"],
            before=data["before"],
            after=data["after"],
            created=data.get("created", False),
            deleted=data.get("deleted", False),
            forced=data.get("forced", False),
            base_ref=data.get("base_ref"),
            compare=data.get("compare", ""),
            commits=data.get("commits", []),
            head_commit=data.get("head_commit")
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
        
        # Prevent feedback loops: Don't process events created by the bot user
        if event.sender.login == mentioned_user:
            logger.info("Event created by bot user, skipping to prevent feedback loop")
            return False
        
        # For comment events, also check if the comment author is the bot
        if isinstance(event, CommentEvent) and event.comment.user.login == mentioned_user:
            logger.info("Comment created by bot user, skipping to prevent feedback loop")
            return False
        
        # Special handling for assignment events, opened events with assignees, AND comment events on assigned/authored issues/PRs
        if (event.action == "assigned" or 
            (event.action == "opened" and isinstance(event, (IssueEvent, PullRequestEvent))) or
            (event.action in ["created", "edited"] and isinstance(event, CommentEvent))):
            
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
            
            elif isinstance(event, CommentEvent):
                # For comment events, check if the parent issue/PR is assigned to the bot
                # For PRs, also check if the bot created it (comments are likely feedback)
                if event.issue:
                    # Check if this "issue" is actually a PR (has pull_request field)
                    is_pr = hasattr(event.issue, 'pull_request') and event.issue.pull_request is not None
                    
                    if is_pr:
                        logger.info("Checking comment's PR assignee and author",
                                   has_assignee=hasattr(event.issue, 'assignee'),
                                   pr_author=event.issue.user.login,
                                   is_pr=True)
                        
                        if hasattr(event.issue, 'assignee'):
                            assignee = event.issue.assignee
                            logger.info("Comment's PR assignee found",
                                       assignee_login=assignee.login if assignee else None,
                                       assignee_is_none=assignee is None)
                        
                        # Also check if bot is the PR author (comments are likely feedback/reviews)
                        if event.issue.user.login == mentioned_user:
                            logger.info("Comment on bot-created PR, processing",
                                       pr_author=event.issue.user.login,
                                       mentioned_user=mentioned_user)
                            assignee = event.issue.user  # Treat author as assignee for processing
                    else:
                        # True issue comment
                        logger.info("Checking comment's issue assignee",
                                   has_assignee=hasattr(event.issue, 'assignee'),
                                   is_pr=False)
                        
                        if hasattr(event.issue, 'assignee'):
                            assignee = event.issue.assignee
                            logger.info("Comment's issue assignee found",
                                       assignee_login=assignee.login if assignee else None,
                                       assignee_is_none=assignee is None)
                
                elif event.pull_request:
                    logger.info("Checking comment's PR assignee and author",
                               has_assignee=hasattr(event.pull_request, 'assignee'),
                               pr_author=event.pull_request.user.login)
                    
                    if hasattr(event.pull_request, 'assignee'):
                        assignee = event.pull_request.assignee
                        logger.info("Comment's PR assignee found",
                                   assignee_login=assignee.login if assignee else None,
                                   assignee_is_none=assignee is None)
                    
                    # Also check if bot is the PR author (comments are likely feedback/reviews)
                    if event.pull_request.user.login == mentioned_user:
                        logger.info("Comment on bot-created PR, processing",
                                   pr_author=event.pull_request.user.login,
                                   mentioned_user=mentioned_user)
                        assignee = event.pull_request.user  # Treat author as assignee for processing
            
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
            # For "opened" and "created" actions, continue to check for mentions
        
        # Check for @mentions
        mentions = event.extract_mentions(mentioned_user)
        logger.info("Checking for mentions",
                   mentions_found=len(mentions),
                   should_process=len(mentions) > 0)
        
        return len(mentions) > 0
    
    @staticmethod
    def should_process_event_for_ci(event: WebhookEvent, devs_options) -> bool:
        """Check if an event should be processed for CI mode.
        
        Args:
            event: Parsed webhook event
            devs_options: DevsOptions configuration for the repository
            
        Returns:
            True if the event should trigger CI processing
        """
        import structlog
        logger = structlog.get_logger()
        
        # CI must be enabled in repository configuration
        if not devs_options or not devs_options.ci_enabled:
            logger.info("CI not enabled for repository", repo=event.repository.full_name)
            return False
        
        logger.info("Checking if event should trigger CI",
                   event_type=type(event).__name__,
                   action=event.action,
                   repo=event.repository.full_name)
        
        # Handle pull request events for CI
        if isinstance(event, PullRequestEvent):
            # Process PR opened, synchronize (new commits), reopened
            ci_pr_actions = ["opened", "synchronize", "reopened"]
            should_process = event.action in ci_pr_actions
            
            logger.info("PR event CI check",
                       action=event.action,
                       ci_pr_actions=ci_pr_actions,
                       should_process=should_process)
            
            return should_process
        
        # Handle push events for CI
        elif isinstance(event, PushEvent):
            # Only process pushes to configured branches
            # Extract branch name from ref (refs/heads/main -> main)
            branch = event.ref.replace('refs/heads/', '') if event.ref.startswith('refs/heads/') else event.ref
            
            # Check if branch is in CI configuration
            ci_branches = devs_options.ci_branches or ["main", "master"]
            should_process = branch in ci_branches
            
            logger.info("Push event CI check",
                       branch=branch,
                       ci_branches=ci_branches,
                       should_process=should_process)
            
            return should_process
        
        # Other event types don't trigger CI
        logger.info("Event type does not trigger CI",
                   event_type=type(event).__name__)
        return False
    
