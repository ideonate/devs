"""GitHub API client using PyGithub."""

from github import Github, Auth
from github.GithubException import GithubException
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timezone
import requests
import structlog

from .app_auth import GitHubAppAuth

logger = structlog.get_logger()


class GitHubClient:
    """GitHub API client using PyGithub."""

    def __init__(self, config):
        """Initialize GitHub client.

        Args:
            config: WebhookConfig instance
        """
        self.config = config
        self.token = config.github_token
        self.app_auth = config.create_github_app_auth("github client")
        # Use the new Auth.Token pattern instead of deprecated login_or_token
        self.github = Github(auth=Auth.Token(self.token))
        
        if self.app_auth:
            logger.info("GitHub API client initialized with PyGithub and GitHub App authentication")
        else:
            logger.info("GitHub API client initialized with PyGithub (personal token only)")
    
    async def _get_auth_headers(self, repo: str, prefer_app_auth: bool = False, installation_id: Optional[str] = None) -> Dict[str, str]:
        """Get authentication headers, preferring GitHub App auth when available.
        
        Args:
            repo: Repository in format "owner/repo"
            prefer_app_auth: Whether to prefer GitHub App auth over personal token
            installation_id: GitHub App installation ID if known from webhook event
            
        Returns:
            Headers dict with Authorization header
        """
        # Try GitHub App auth first if available and preferred
        if prefer_app_auth and self.app_auth:
            # If we have an installation ID from a webhook event, use it directly
            if installation_id:
                app_headers = await self.app_auth.get_auth_headers_for_installation(installation_id)
            else:
                app_headers = await self.app_auth.get_auth_headers(repo)
                
            if app_headers:
                logger.debug("Using GitHub App authentication", repo=repo, installation_id=installation_id)
                return app_headers
            else:
                logger.warning("GitHub App auth failed, falling back to personal token", repo=repo, installation_id=installation_id)
        
        # Fall back to personal token
        logger.debug("Using personal token authentication", repo=repo)
        return {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    
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
            
            headers = await self._get_auth_headers(repo, prefer_app_auth=False)
            
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
    
    # GitHub Checks API methods
    
    async def create_check_run(
        self,
        repo: str,
        name: str,
        head_sha: str,
        status: str = "queued",
        details_url: Optional[str] = None,
        external_id: Optional[str] = None,
        installation_id: Optional[str] = None
    ) -> Optional[int]:
        """Create a check run using GitHub Checks API.
        
        Args:
            repo: Repository in format "owner/repo"
            name: Name of the check run (e.g., "tests")
            head_sha: SHA of the commit to run checks on
            status: Status of check run (queued, in_progress, completed)
            details_url: URL to external build/test results
            external_id: External identifier for the check run
            installation_id: GitHub App installation ID if known from webhook event
            
        Returns:
            Check run ID if successful, None otherwise
        """
        try:
            headers = await self._get_auth_headers(repo, prefer_app_auth=True, installation_id=installation_id)
            
            data = {
                'name': name,
                'head_sha': head_sha,
                'status': status,
                'started_at': datetime.now(timezone.utc).isoformat()
            }
            
            if details_url:
                data['details_url'] = details_url
            if external_id:
                data['external_id'] = external_id
                
            url = f'https://api.github.com/repos/{repo}/check-runs'
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 201:
                check_run = response.json()
                check_run_id = check_run['id']
                logger.info("Check run created",
                           repo=repo, name=name, check_run_id=check_run_id, head_sha=head_sha)
                return check_run_id
            else:
                logger.error("Failed to create check run",
                            repo=repo, name=name, head_sha=head_sha, 
                            status=response.status_code, error=response.text)
                return None
                
        except Exception as e:
            logger.error("Unexpected error creating check run",
                        repo=repo, name=name, head_sha=head_sha, error=str(e))
            return None
    
    async def update_check_run(
        self,
        repo: str,
        check_run_id: int,
        status: str,
        conclusion: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None,
        details_url: Optional[str] = None,
        installation_id: Optional[str] = None
    ) -> bool:
        """Update a check run using GitHub Checks API.
        
        Args:
            repo: Repository in format "owner/repo"
            check_run_id: ID of the check run to update
            status: Status of check run (queued, in_progress, completed)
            conclusion: Conclusion when status=completed (success, failure, neutral, cancelled, skipped, timed_out, action_required)
            output: Output object with title, summary, text, annotations, images
            details_url: URL to external build/test results
            installation_id: GitHub App installation ID if known from webhook event
            
        Returns:
            True if successful
        """
        try:
            headers = await self._get_auth_headers(repo, prefer_app_auth=True, installation_id=installation_id)
            
            data = {
                'status': status
            }
            
            if status == 'completed':
                data['completed_at'] = datetime.now(timezone.utc).isoformat()
                if conclusion:
                    data['conclusion'] = conclusion
            
            if output:
                data['output'] = output
            if details_url:
                data['details_url'] = details_url
                
            url = f'https://api.github.com/repos/{repo}/check-runs/{check_run_id}'
            response = requests.patch(url, json=data, headers=headers)
            
            if response.status_code == 200:
                logger.info("Check run updated",
                           repo=repo, check_run_id=check_run_id, status=status, conclusion=conclusion)
                return True
            else:
                logger.error("Failed to update check run",
                            repo=repo, check_run_id=check_run_id, status=status,
                            response_status=response.status_code, error=response.text)
                return False
                
        except Exception as e:
            logger.error("Unexpected error updating check run",
                        repo=repo, check_run_id=check_run_id, status=status, error=str(e))
            return False
    
    async def complete_check_run_success(
        self,
        repo: str,
        check_run_id: int,
        title: str = "Tests passed",
        summary: str = "All tests completed successfully",
        text: Optional[str] = None,
        details_url: Optional[str] = None,
        installation_id: Optional[str] = None
    ) -> bool:
        """Complete a check run with success status.

        Args:
            repo: Repository in format "owner/repo"
            check_run_id: ID of the check run to complete
            title: Title for the check run output
            summary: Summary text for the check run
            text: Additional detailed text output (e.g., test reports)
            details_url: URL to external build/test results
            installation_id: GitHub App installation ID if known from webhook event

        Returns:
            True if successful
        """
        output = {
            'title': title,
            'summary': summary
        }

        if text:
            output['text'] = text

        return await self.update_check_run(
            repo=repo,
            check_run_id=check_run_id,
            status='completed',
            conclusion='success',
            output=output,
            details_url=details_url,
            installation_id=installation_id
        )
    
    async def complete_check_run_failure(
        self,
        repo: str,
        check_run_id: int,
        title: str = "Tests failed",
        summary: str = "Some tests failed",
        text: Optional[str] = None,
        details_url: Optional[str] = None,
        installation_id: Optional[str] = None
    ) -> bool:
        """Complete a check run with failure status.
        
        Args:
            repo: Repository in format "owner/repo"
            check_run_id: ID of the check run to complete
            title: Title for the check run output
            summary: Summary text for the check run
            text: Additional detailed text output
            details_url: URL to external build/test results
            installation_id: GitHub App installation ID if known from webhook event
            
        Returns:
            True if successful
        """
        output = {
            'title': title,
            'summary': summary
        }
        
        if text:
            output['text'] = text
        
        return await self.update_check_run(
            repo=repo,
            check_run_id=check_run_id,
            status='completed',
            conclusion='failure',
            output=output,
            details_url=details_url,
            installation_id=installation_id
        )