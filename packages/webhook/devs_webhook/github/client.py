"""GitHub API client using PyGithub."""

from github import Github
from github.GithubException import GithubException
from typing import Optional, Dict, Any, List
from pathlib import Path
import structlog

logger = structlog.get_logger()


class GitHubClient:
    """GitHub API client using PyGithub."""
    
    def __init__(self, token: str):
        """Initialize GitHub client.
        
        Args:
            token: GitHub personal access token
        """
        self.token = token
        self.github = Github(token)
        logger.info("GitHub API client initialized with PyGithub")
    
    async def comment_on_issue(
        self, 
        repo: str, 
        issue_number: int, 
        comment: str
    ) -> bool:
        """Add a comment to a GitHub issue.
        
        Args:
            repo: Repository in format "owner/repo"
            issue_number: Issue number
            comment: Comment text
            
        Returns:
            True if successful
        """
        try:
            repository = self.github.get_repo(repo)
            issue = repository.get_issue(issue_number)
            issue.create_comment(comment)
            
            logger.info("Comment added to issue", repo=repo, issue=issue_number)
            return True
            
        except GithubException as e:
            logger.error("Failed to comment on issue", 
                        repo=repo, issue=issue_number, error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error commenting on issue", 
                        repo=repo, issue=issue_number, error=str(e))
            return False
    
    async def comment_on_pr(
        self, 
        repo: str, 
        pr_number: int, 
        comment: str
    ) -> bool:
        """Add a comment to a GitHub pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            comment: Comment text
            
        Returns:
            True if successful
        """
        try:
            repository = self.github.get_repo(repo)
            pull_request = repository.get_pull(pr_number)
            pull_request.create_issue_comment(comment)
            
            logger.info("Comment added to PR", repo=repo, pr=pr_number)
            return True
            
        except GithubException as e:
            logger.error("Failed to comment on PR",
                        repo=repo, pr=pr_number, error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error commenting on PR",
                        repo=repo, pr=pr_number, error=str(e))
            return False
    
    async def get_repository_info(self, repo: str) -> Optional[Dict[str, Any]]:
        """Get repository information.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            Repository info dict or None if failed
        """
        try:
            repository = self.github.get_repo(repo)
            return {
                "name": repository.name,
                "full_name": repository.full_name,
                "owner": repository.owner.login,
                "url": repository.html_url,
                "clone_url": repository.clone_url,
                "ssh_url": repository.ssh_url,
                "default_branch": repository.default_branch
            }
            
        except GithubException as e:
            logger.error("Failed to get repository info", repo=repo, error=str(e))
            return None
        except Exception as e:
            logger.error("Unexpected error getting repository info", repo=repo, error=str(e))
            return None