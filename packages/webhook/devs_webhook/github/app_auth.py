"""GitHub App authentication for enhanced API access."""

import time
import jwt
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import structlog

logger = structlog.get_logger()


class GitHubAppAuth:
    """GitHub App authentication handler for generating installation tokens."""
    
    def __init__(self, app_id: str, private_key: str, installation_id: Optional[str] = None):
        """Initialize GitHub App authentication.
        
        Args:
            app_id: GitHub App ID
            private_key: Private key content in PEM format
            installation_id: Installation ID (optional, can be auto-discovered)
        """
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self._installation_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
    def _generate_jwt_token(self) -> str:
        """Generate a JWT token for GitHub App authentication.
        
        Returns:
            JWT token for authenticating as the GitHub App
        """
        now = datetime.now(timezone.utc)
        
        payload = {
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(minutes=5)).timestamp()),  # 5 minutes max
            'iss': self.app_id
        }
        
        return jwt.encode(payload, self.private_key, algorithm='RS256')
    
    async def _get_installation_id(self, repo: str) -> Optional[str]:
        """Auto-discover installation ID for a repository.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            Installation ID if found, None otherwise
        """
        if self.installation_id:
            return self.installation_id
            
        try:
            jwt_token = self._generate_jwt_token()
            headers = {
                'Authorization': f'Bearer {jwt_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get installations for this app
            url = 'https://api.github.com/app/installations'
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error("Failed to get app installations", 
                           status=response.status_code, error=response.text)
                return None
                
            installations = response.json()
            
            # Find installation for the repository
            for installation in installations:
                install_id = str(installation['id'])
                
                # Check if this installation has access to the repository
                repo_url = f'https://api.github.com/installation/repositories'
                install_headers = await self._get_installation_headers(install_id)
                if install_headers:
                    repo_response = requests.get(repo_url, headers=install_headers)
                    if repo_response.status_code == 200:
                        repos = repo_response.json().get('repositories', [])
                        for repository in repos:
                            if repository['full_name'] == repo:
                                logger.info("Auto-discovered installation ID", 
                                          installation_id=install_id, repo=repo)
                                self.installation_id = install_id
                                return install_id
            
            logger.warning("No installation found for repository", repo=repo)
            return None
            
        except Exception as e:
            logger.error("Error auto-discovering installation ID", 
                        repo=repo, error=str(e))
            return None
    
    async def _get_installation_headers(self, installation_id: str) -> Optional[Dict[str, str]]:
        """Get headers with a valid installation access token.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Headers dict with Authorization header, or None if failed
        """
        token = await self._get_installation_token(installation_id)
        if not token:
            return None
            
        return {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    async def _get_installation_token(self, installation_id: str) -> Optional[str]:
        """Get or refresh installation access token.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Installation access token or None if failed
        """
        # Check if we have a valid cached token
        if (self._installation_token and 
            self._token_expires_at and 
            self._token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=5)):
            return self._installation_token
            
        # Generate new installation token
        try:
            jwt_token = self._generate_jwt_token()
            headers = {
                'Authorization': f'Bearer {jwt_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            url = f'https://api.github.com/app/installations/{installation_id}/access_tokens'
            response = requests.post(url, headers=headers)
            
            if response.status_code == 201:
                token_data = response.json()
                self._installation_token = token_data['token']
                expires_at_str = token_data['expires_at']
                self._token_expires_at = datetime.fromisoformat(
                    expires_at_str.replace('Z', '+00:00')
                )
                
                logger.info("Generated new installation token", 
                           installation_id=installation_id,
                           expires_at=expires_at_str)
                return self._installation_token
            else:
                logger.error("Failed to get installation token",
                           installation_id=installation_id,
                           status=response.status_code, error=response.text)
                return None
                
        except Exception as e:
            logger.error("Error generating installation token",
                        installation_id=installation_id, error=str(e))
            return None
    
    async def get_auth_headers(self, repo: str) -> Optional[Dict[str, str]]:
        """Get authentication headers for a specific repository.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            Headers dict with Authorization header, or None if authentication failed
        """
        # Get or discover installation ID
        installation_id = await self._get_installation_id(repo)
        if not installation_id:
            return None
            
        return await self._get_installation_headers(installation_id)
    
    async def get_auth_headers_for_installation(self, installation_id: str) -> Optional[Dict[str, str]]:
        """Get authentication headers for a specific installation ID.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Headers dict with Authorization header, or None if authentication failed
        """
        return await self._get_installation_headers(installation_id)
    
    async def test_authentication(self, repo: str) -> bool:
        """Test GitHub App authentication for a repository.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            True if authentication successful
        """
        headers = await self.get_auth_headers(repo)
        if not headers:
            return False
            
        try:
            # Test by making a simple API call
            url = f'https://api.github.com/repos/{repo}'
            response = requests.get(url, headers=headers)
            
            success = response.status_code == 200
            if success:
                logger.info("GitHub App authentication test successful", repo=repo)
            else:
                logger.error("GitHub App authentication test failed",
                           repo=repo, status=response.status_code, error=response.text)
            
            return success
            
        except Exception as e:
            logger.error("Error testing GitHub App authentication",
                        repo=repo, error=str(e))
            return False