"""GitHub webhook payload models."""

import re
import hashlib
from typing import Optional, Dict, Any, List, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field, Discriminator, Tag
from datetime import datetime


class GitHubInstallation(BaseModel):
    """GitHub App installation model."""
    id: int
    account: Optional[Dict[str, Any]] = None


class GitHubUser(BaseModel):
    """GitHub user model."""
    login: str
    id: int
    avatar_url: str
    html_url: str


class GitHubRepository(BaseModel):
    """GitHub repository model."""
    id: int
    name: str
    full_name: str
    owner: GitHubUser
    html_url: str
    clone_url: str
    ssh_url: str
    default_branch: str = "main"


class GitHubIssue(BaseModel):
    """GitHub issue model."""
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    assignee: Optional[GitHubUser] = None
    html_url: str
    created_at: datetime
    updated_at: datetime
    comments: int = 0
    
    # Additional fields that may be present for PRs treated as issues
    draft: Optional[bool] = None
    pull_request: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")  # Ignore additional fields not in model


class GitHubPullRequest(BaseModel):
    """GitHub pull request model."""
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    assignee: Optional[GitHubUser] = None
    html_url: str
    head: Dict[str, Any]
    base: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GitHubComment(BaseModel):
    """GitHub comment model."""
    id: int
    body: str
    user: GitHubUser
    html_url: str
    created_at: datetime
    updated_at: datetime


class WebhookEvent(BaseModel):
    """Base webhook event model."""
    action: str
    repository: GitHubRepository
    sender: GitHubUser
    installation: Optional[GitHubInstallation] = None
    is_test: bool = Field(default=False, description="Indicates if this is a test event")
    
    def extract_mentions(self, target_user: str) -> List[str]:
        """Extract @mentions of target user from relevant text."""
        mentions = []
        text_sources = self._get_text_sources()
        
        # Create regex pattern with word boundary to match exact username
        # This prevents matching @bot in @botname or @mybotname
        pattern = re.compile(rf"@{re.escape(target_user)}\b", re.IGNORECASE)
        
        for text in text_sources:
            if text and pattern.search(text):
                mentions.append(text)
        
        return mentions
    
    def _get_text_sources(self) -> List[Optional[str]]:
        """Get text sources to search for mentions. Override in subclasses."""
        return []
    
    def get_context_for_claude(self) -> str:
        """Get formatted context for Claude Code. Override in subclasses."""
        return f"Repository: {self.repository.full_name}\nAction: {self.action}"
    
    def get_content_hash(self) -> Optional[str]:
        """Get hash of content that would be sent to Claude for deduplication."""
        return None


class IssueEvent(WebhookEvent):
    """GitHub issue webhook event."""
    issue: GitHubIssue
    
    def _get_text_sources(self) -> List[Optional[str]]:
        return [self.issue.title, self.issue.body]
    
    def get_context_for_claude(self) -> str:
        return f"""GitHub Issue #{self.issue.number} in {self.repository.full_name}

Title: {self.issue.title}
URL: {self.issue.html_url}
State: {self.issue.state}
Created by: @{self.issue.user.login}

Description:
{self.issue.body or "No description provided"}

Action: {self.action}
Repository: {self.repository.full_name}
Clone URL: {self.repository.clone_url}
"""

    def get_content_hash(self) -> str:
        """Get hash of issue content for deduplication."""
        # Hash the content that matters to Claude - excludes action field
        content_parts = [
            str(self.repository.full_name),
            str(self.issue.number),
            str(self.issue.title),
            str(self.issue.body or ""),
            str(self.issue.assignee.login if self.issue.assignee else ""),
            str(self.issue.updated_at),
            str(self.issue.comments)
        ]
        content_string = "|".join(content_parts)
        return hashlib.sha256(content_string.encode()).hexdigest()[:16]


class PullRequestEvent(WebhookEvent):
    """GitHub pull request webhook event."""
    pull_request: GitHubPullRequest
    
    def _get_text_sources(self) -> List[Optional[str]]:
        return [self.pull_request.title, self.pull_request.body]
    
    def get_context_for_claude(self) -> str:
        return f"""GitHub Pull Request #{self.pull_request.number} in {self.repository.full_name}

Title: {self.pull_request.title}
URL: {self.pull_request.html_url}
State: {self.pull_request.state}
Created by: @{self.pull_request.user.login}

Description:
{self.pull_request.body or "No description provided"}

Source Branch: {self.pull_request.head.get('ref', 'unknown')}
Target Branch: {self.pull_request.base.get('ref', 'unknown')}

Action: {self.action}
Repository: {self.repository.full_name}
Clone URL: {self.repository.clone_url}
"""

    def get_content_hash(self) -> str:
        """Get hash of PR content for deduplication."""
        content_parts = [
            str(self.repository.full_name),
            str(self.pull_request.number),
            str(self.pull_request.title),
            str(self.pull_request.body or ""),
            str(self.pull_request.assignee.login if self.pull_request.assignee else ""),
            str(self.pull_request.updated_at),
            str(self.pull_request.head.get('ref', '')),
            str(self.pull_request.base.get('ref', ''))
        ]
        content_string = "|".join(content_parts)
        return hashlib.sha256(content_string.encode()).hexdigest()[:16]


class CommentEvent(WebhookEvent):
    """GitHub comment webhook event."""
    comment: GitHubComment
    issue: Optional[GitHubIssue] = None  # For issue comments
    pull_request: Optional[GitHubPullRequest] = None  # For PR comments
    
    def _get_text_sources(self) -> List[Optional[str]]:
        sources = [self.comment.body]
        if self.issue:
            sources.extend([self.issue.title, self.issue.body])
        if self.pull_request:
            sources.extend([self.pull_request.title, self.pull_request.body])
        return sources
    
    def get_context_for_claude(self) -> str:
        if self.issue:
            context_type = f"Comment on Issue #{self.issue.number}"
            parent_info = f"""
Original Issue:
Title: {self.issue.title}
Description: {self.issue.body or "No description"}
URL: {self.issue.html_url}
"""
        elif self.pull_request:
            context_type = f"Comment on Pull Request #{self.pull_request.number}"
            parent_info = f"""
Original Pull Request:
Title: {self.pull_request.title}
Description: {self.pull_request.body or "No description"}
URL: {self.pull_request.html_url}
Source Branch: {self.pull_request.head.get('ref', 'unknown')}
Target Branch: {self.pull_request.base.get('ref', 'unknown')}
"""
        else:
            context_type = "Comment"
            parent_info = ""
        
        return f"""{context_type} in {self.repository.full_name}

Comment by @{self.comment.user.login}:
{self.comment.body}

Comment URL: {self.comment.html_url}
{parent_info}
Action: {self.action}
Repository: {self.repository.full_name}
Clone URL: {self.repository.clone_url}
"""
    
    def get_content_hash(self) -> str:
        """Get hash of comment content for deduplication."""
        # Comments are always processed since they represent new input
        # But include timestamp to distinguish different comments
        content_parts = [
            str(self.repository.full_name),
            str(self.comment.id),
            str(self.comment.body),
            str(self.comment.created_at),
            str(self.comment.user.login)
        ]
        
        # Include parent issue/PR info if available
        if self.issue:
            content_parts.extend([
                "issue",
                str(self.issue.number),
                str(self.issue.updated_at)
            ])
        elif self.pull_request:
            content_parts.extend([
                "pr", 
                str(self.pull_request.number),
                str(self.pull_request.updated_at)
            ])
            
        content_string = "|".join(content_parts)
        return hashlib.sha256(content_string.encode()).hexdigest()[:16]
    
class TestIssueEvent(IssueEvent):
    """Test event for issues, used in unit tests."""

    is_test: bool = True  # Mark as test event

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **data):
        super().__init__(**data)
        self.action = "opened"  # Default action for test events

    def get_context_for_claude(self) -> str:
        return f"""Test event. """


class GitHubCommit(BaseModel):
    """GitHub commit model."""
    id: str
    message: str
    timestamp: datetime
    url: str
    author: Dict[str, Any]
    committer: Dict[str, Any]
    added: List[str] = []
    removed: List[str] = []
    modified: List[str] = []


class GitHubPush(BaseModel):
    """GitHub push model."""
    ref: str
    before: str
    after: str
    created: bool
    deleted: bool
    forced: bool
    base_ref: Optional[str] = None
    compare: str
    commits: List[GitHubCommit]
    head_commit: Optional[GitHubCommit] = None


class PushEvent(WebhookEvent):
    """GitHub push webhook event."""
    ref: str
    before: str
    after: str
    created: bool = False
    deleted: bool = False
    forced: bool = False
    base_ref: Optional[str] = None
    compare: str = ""
    commits: List[Dict[str, Any]] = []
    head_commit: Optional[Dict[str, Any]] = None
    
    def _get_text_sources(self) -> List[Optional[str]]:
        # Push events don't have text to search for mentions
        return []
    
    def get_context_for_claude(self) -> str:
        branch = self.ref.replace('refs/heads/', '') if self.ref.startswith('refs/heads/') else self.ref
        
        return f"""GitHub Push to {self.repository.full_name}
        
Branch: {branch}
Pushed by: @{self.sender.login}
Commits: {len(self.commits)}

Latest commit: {self.head_commit['message'] if self.head_commit else 'No commits'}
Compare: {self.compare}

Action: {self.action}
Repository: {self.repository.full_name}
Clone URL: {self.repository.clone_url}
"""

    def get_content_hash(self) -> str:
        """Get hash of push content for deduplication."""
        content_parts = [
            str(self.repository.full_name),
            str(self.ref),
            str(self.after),  # The commit SHA being pushed
            str(len(self.commits)),
            str(self.head_commit['message'] if self.head_commit else '')
        ]
        content_string = "|".join(content_parts)
        return hashlib.sha256(content_string.encode()).hexdigest()[:16]


class TestPushEvent(PushEvent):
    """Test event for push/CI, used for local testing of runtests functionality."""

    is_test: bool = True  # Mark as test event to skip GitHub Checks API calls

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def get_context_for_claude(self) -> str:
        return f"""Test push event for CI testing."""


class TestPullRequestEvent(PullRequestEvent):
    """Test event for PR/CI, used for local testing of PR runtests functionality."""

    is_test: bool = True  # Mark as test event to skip GitHub Checks API calls

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def get_context_for_claude(self) -> str:
        return f"""Test pull request event for CI testing."""


# Discriminated union for automatic event type detection
def get_webhook_event_discriminator(v: Any) -> str:
    """Discriminator function to determine webhook event type."""
    if isinstance(v, dict):
        if 'comment' in v:
            return 'comment'
        elif 'ref' in v and 'commits' in v:
            return 'push'
        elif 'issue' in v and ('pull_request' not in v or v.get('pull_request') is None):
            return 'issue'
        elif 'pull_request' in v and v.get('pull_request') is not None:
            return 'pull_request'
    return 'comment'  # Default fallback


AnyWebhookEvent = Annotated[
    Union[
        Annotated[CommentEvent, Tag('comment')],
        Annotated[IssueEvent, Tag('issue')],
        Annotated[PullRequestEvent, Tag('pull_request')],
        Annotated[PushEvent, Tag('push')]
    ],
    Discriminator(get_webhook_event_discriminator)
]