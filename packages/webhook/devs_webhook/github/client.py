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
    
    async def add_reaction_to_issue(
        self,
        repo: str,
        issue_number: int,
        reaction: str = "eyes"
    ) -> bool:
        """Add a reaction to a GitHub issue.
        
        Args:
            repo: Repository in format "owner/repo"
            issue_number: Issue number
            reaction: Reaction type (eyes, +1, -1, laugh, confused, heart, hooray, rocket)
            
        Returns:
            True if successful
        """
        try:
            repository = self.github.get_repo(repo)
            issue = repository.get_issue(issue_number)
            issue.create_reaction(reaction)
            
            logger.info("Reaction added to issue", 
                       repo=repo, issue=issue_number, reaction=reaction)
            return True
            
        except GithubException as e:
            logger.error("Failed to add reaction to issue",
                        repo=repo, issue=issue_number, reaction=reaction, error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error adding reaction to issue",
                        repo=repo, issue=issue_number, reaction=reaction, error=str(e))
            return False
    
    async def add_reaction_to_pr(
        self,
        repo: str,
        pr_number: int,
        reaction: str = "eyes"
    ) -> bool:
        """Add a reaction to a GitHub pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            reaction: Reaction type (eyes, +1, -1, laugh, confused, heart, hooray, rocket)
            
        Returns:
            True if successful
        """
        try:
            repository = self.github.get_repo(repo)
            # PRs are issues in GitHub's API, so we can use get_issue
            pr_as_issue = repository.get_issue(pr_number)
            pr_as_issue.create_reaction(reaction)
            
            logger.info("Reaction added to PR",
                       repo=repo, pr=pr_number, reaction=reaction)
            return True
            
        except GithubException as e:
            logger.error("Failed to add reaction to PR",
                        repo=repo, pr=pr_number, reaction=reaction, error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error adding reaction to PR",
                        repo=repo, pr=pr_number, reaction=reaction, error=str(e))
            return False
    
    async def add_reaction_to_comment(
        self,
        repo: str,
        comment_id: int,
        reaction: str = "eyes"
    ) -> bool:
        """Add a reaction to a GitHub comment.
        
        Args:
            repo: Repository in format "owner/repo"
            comment_id: Comment ID
            reaction: Reaction type (eyes, +1, -1, laugh, confused, heart, hooray, rocket)
            
        Returns:
            True if successful
        """
        try:
            # PyGithub's repository.get_comment() gets commit comments, not issue comments.
            # For issue/PR comments, we need to use the REST API directly.
            import requests
            
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Add reaction to issue/PR comment via REST API
            reaction_url = f'https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions'
            response = requests.post(
                reaction_url, 
                json={'content': reaction},
                headers=headers
            )
            
            if response.status_code in [200, 201]:
                logger.info("Reaction added to comment",
                           repo=repo, comment_id=comment_id, reaction=reaction)
                return True
            else:
                logger.error("Failed to add reaction to comment",
                            repo=repo, comment_id=comment_id, reaction=reaction, 
                            status=response.status_code, error=response.text)
                return False
            
        except Exception as e:
            logger.error("Unexpected error adding reaction to comment",
                        repo=repo, comment_id=comment_id, reaction=reaction, error=str(e))
            return False