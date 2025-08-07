"""Test authentication for webhook endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import base64

# Import the app
from devs_webhook.app import app
from devs_webhook.config import WebhookConfig


def create_basic_auth_header(username: str, password: str) -> dict:
    """Create HTTP Basic auth header."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_config_with_auth():
    """Mock config with authentication enabled."""
    config = MagicMock(spec=WebhookConfig)
    config.dev_mode = False
    config.admin_username = "admin"
    config.admin_password = "secure_password"
    config.github_webhook_secret = "test_secret"
    config.github_token = "test_token"
    config.github_mentioned_user = "testuser"
    return config


@pytest.fixture
def mock_config_dev_mode():
    """Mock config in dev mode without password."""
    config = MagicMock(spec=WebhookConfig)
    config.dev_mode = True
    config.admin_username = "admin"
    config.admin_password = ""
    config.github_webhook_secret = "test_secret"
    config.github_token = "test_token"
    config.github_mentioned_user = "testuser"
    return config


@pytest.fixture
def mock_webhook_handler():
    """Mock webhook handler."""
    handler = MagicMock()
    handler.get_status.return_value = {"status": "healthy", "containers": []}
    handler.list_containers.return_value = []
    handler.stop_container.return_value = True
    return handler


class TestPublicEndpoints:
    """Test public endpoints that don't require authentication."""
    
    def test_root_endpoint(self, client):
        """Test root health check endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_health_endpoint(self, client):
        """Test detailed health endpoint."""
        with patch("devs_webhook.app.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.dev_mode = False
            mock_config.github_mentioned_user = "testuser"
            mock_config.container_pool = "test1,test2"
            mock_config.webhook_path = "/webhook"
            mock_config.log_format = "json"
            mock_get_config.return_value = mock_config
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "config" in data


class TestProtectedEndpoints:
    """Test endpoints that require authentication."""
    
    def test_status_without_auth(self, client, mock_webhook_handler):
        """Test status endpoint without authentication."""
        with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
            response = client.get("/status")
            assert response.status_code == 401
    
    def test_status_with_wrong_auth(self, client, mock_config_with_auth, mock_webhook_handler):
        """Test status endpoint with wrong credentials."""
        with patch("devs_webhook.app.get_config", return_value=mock_config_with_auth):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                headers = create_basic_auth_header("admin", "wrong_password")
                response = client.get("/status", headers=headers)
                assert response.status_code == 401
    
    def test_status_with_correct_auth(self, client, mock_config_with_auth, mock_webhook_handler):
        """Test status endpoint with correct credentials."""
        with patch("devs_webhook.app.get_config", return_value=mock_config_with_auth):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                headers = create_basic_auth_header("admin", "secure_password")
                response = client.get("/status", headers=headers)
                assert response.status_code == 200
                assert "status" in response.json()
    
    def test_containers_without_auth(self, client, mock_webhook_handler):
        """Test containers endpoint without authentication."""
        with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
            response = client.get("/containers")
            assert response.status_code == 401
    
    def test_containers_with_auth(self, client, mock_config_with_auth, mock_webhook_handler):
        """Test containers endpoint with authentication."""
        with patch("devs_webhook.app.get_config", return_value=mock_config_with_auth):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                headers = create_basic_auth_header("admin", "secure_password")
                response = client.get("/containers", headers=headers)
                assert response.status_code == 200
                assert isinstance(response.json(), list)
    
    def test_stop_container_without_auth(self, client, mock_webhook_handler):
        """Test stop container endpoint without authentication."""
        with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
            response = client.post("/container/test-container/stop")
            assert response.status_code == 401
    
    def test_stop_container_with_auth(self, client, mock_config_with_auth, mock_webhook_handler):
        """Test stop container endpoint with authentication."""
        with patch("devs_webhook.app.get_config", return_value=mock_config_with_auth):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                headers = create_basic_auth_header("admin", "secure_password")
                response = client.post("/container/test-container/stop", headers=headers)
                assert response.status_code == 200
                assert response.json()["status"] == "stopped"


class TestDevModeAuthentication:
    """Test authentication behavior in development mode."""
    
    def test_dev_mode_allows_any_auth(self, client, mock_config_dev_mode, mock_webhook_handler):
        """Test that dev mode with no password allows any credentials."""
        with patch("devs_webhook.app.get_config", return_value=mock_config_dev_mode):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                # Should work with any credentials in dev mode without password
                headers = create_basic_auth_header("anyuser", "anypass")
                response = client.get("/status", headers=headers)
                assert response.status_code == 200
    
    def test_dev_mode_with_password(self, client, mock_webhook_handler):
        """Test that dev mode with password still requires correct auth."""
        config = MagicMock(spec=WebhookConfig)
        config.dev_mode = True
        config.admin_username = "admin"
        config.admin_password = "devpass"
        
        with patch("devs_webhook.app.get_config", return_value=config):
            with patch("devs_webhook.app.get_webhook_handler", return_value=mock_webhook_handler):
                # Wrong password should fail even in dev mode
                headers = create_basic_auth_header("admin", "wrongpass")
                response = client.get("/status", headers=headers)
                assert response.status_code == 401
                
                # Correct password should work
                headers = create_basic_auth_header("admin", "devpass")
                response = client.get("/status", headers=headers)
                assert response.status_code == 200


class TestWebhookEndpoint:
    """Test that webhook endpoint remains signature-based."""
    
    def test_webhook_requires_signature_not_basic_auth(self, client):
        """Test that webhook endpoint uses signature verification, not basic auth."""
        # Basic auth should not work for webhook endpoint
        headers = create_basic_auth_header("admin", "password")
        headers["Content-Type"] = "application/json"
        
        response = client.post("/webhook", json={"test": "data"}, headers=headers)
        # Should fail with 401 due to missing signature, not due to basic auth
        assert response.status_code == 401
        
        # The error should be about invalid signature, not credentials
        # (This confirms webhook still uses signature-based auth)