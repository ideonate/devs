"""GitHub API client using gh CLI."""

import subprocess
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
import structlog

logger = structlog.get_logger()


class GitHubClient:
    """GitHub API client using the gh CLI."""
    
    def __init__(self, token: str):
        """Initialize GitHub client.
        
        Args:
            token: GitHub personal access token
        """
        self.token = token
        self._setup_auth()
    
    def _setup_auth(self) -> None:
        """Set up GitHub CLI authentication."""
        try:
            # Set the token for gh CLI
            env = {"GH_TOKEN": self.token}
            result = subprocess.run(
                ["gh", "auth", "status"],
                env=env,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                logger.warning("GitHub CLI auth not configured", stderr=result.stderr)
            else:
                logger.info("GitHub CLI authenticated successfully")
                
        except FileNotFoundError:
            logger.error("GitHub CLI (gh) not found. Install with: brew install gh")
            raise
    
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
            env = {"GH_TOKEN": self.token}
            result = subprocess.run([
                "gh", "issue", "comment", str(issue_number),
                "--repo", repo,
                "--body", comment
            ], env=env, capture_output=True, text=True, check=True)
            
            logger.info("Comment added to issue", repo=repo, issue=issue_number)
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to comment on issue", 
                        repo=repo, issue=issue_number, error=e.stderr)
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
            env = {"GH_TOKEN": self.token}
            result = subprocess.run([
                "gh", "pr", "comment", str(pr_number),
                "--repo", repo,
                "--body", comment
            ], env=env, capture_output=True, text=True, check=True)
            
            logger.info("Comment added to PR", repo=repo, pr=pr_number)
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to comment on PR",
                        repo=repo, pr=pr_number, error=e.stderr)
            return False
    
    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        working_dir: Optional[Path] = None
    ) -> Optional[int]:
        """Create a pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            title: PR title
            body: PR description
            head_branch: Source branch
            base_branch: Target branch
            working_dir: Directory to run command from
            
        Returns:
            PR number if successful, None otherwise
        """
        try:
            env = {"GH_TOKEN": self.token}
            cmd = [
                "gh", "pr", "create",
                "--repo", repo,
                "--title", title,
                "--body", body,
                "--head", head_branch,
                "--base", base_branch
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Extract PR number from output URL
            pr_url = result.stdout.strip()
            pr_number = int(pr_url.split("/")[-1])
            
            logger.info("Pull request created", 
                       repo=repo, pr_number=pr_number, branch=head_branch)
            return pr_number
            
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error("Failed to create pull request",
                        repo=repo, branch=head_branch, error=str(e))
            return None
    
    async def get_repository_info(self, repo: str) -> Optional[Dict[str, Any]]:
        """Get repository information.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            Repository info dict or None if failed
        """
        try:
            env = {"GH_TOKEN": self.token}
            result = subprocess.run([
                "gh", "repo", "view", repo, "--json",
                "name,owner,url,cloneUrl,sshUrl,defaultBranch"
            ], env=env, capture_output=True, text=True, check=True)
            
            return json.loads(result.stdout)
            
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.error("Failed to get repository info", repo=repo, error=str(e))
            return None
    
    async def clone_repository(
        self, 
        repo: str, 
        destination: Path,
        branch: Optional[str] = None
    ) -> bool:
        """Clone a repository.
        
        Args:
            repo: Repository in format "owner/repo"
            destination: Local directory to clone to
            branch: Specific branch to clone
            
        Returns:
            True if successful
        """
        try:
            env = {"GH_TOKEN": self.token}
            cmd = ["gh", "repo", "clone", repo, str(destination)]
            
            if branch:
                cmd.extend(["--", "--branch", branch])
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info("Repository cloned", repo=repo, destination=str(destination))
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to clone repository",
                        repo=repo, destination=str(destination), error=e.stderr)
            return False