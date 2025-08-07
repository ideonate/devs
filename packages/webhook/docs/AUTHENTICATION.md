# Webhook Authentication

## Overview

The webhook service uses two types of authentication:

1. **GitHub Webhook Signature Verification** - For the `/webhook` endpoint that receives GitHub events
2. **HTTP Basic Authentication** - For admin endpoints that manage containers and view status

## Endpoints and Authentication

### Public Endpoints (No Authentication Required)

- `GET /` - Basic health check
- `GET /health` - Detailed health check with configuration info

### GitHub Webhook Endpoint

- `POST /webhook` - Receives GitHub webhook events
  - Authentication: GitHub webhook signature verification using `GITHUB_WEBHOOK_SECRET`
  - The signature is verified using HMAC-SHA256

### Admin Endpoints (HTTP Basic Auth Required)

- `GET /status` - Get webhook handler status
- `GET /containers` - List all managed containers  
- `POST /container/{container_name}/stop` - Stop a specific container

These endpoints require HTTP Basic Authentication with the configured admin credentials.

### Development Endpoints

- `POST /testevent` - Test endpoint (only available when `DEV_MODE=true`)
  - In dev mode: Requires HTTP Basic Auth
  - In production: Returns 404

## Configuration

Add these environment variables to your `.env` file or set them in your environment:

```bash
# Admin credentials for protected endpoints
ADMIN_USERNAME=admin              # Default: "admin"
ADMIN_PASSWORD=your-secure-password-here  # Required in production

# Development mode flag
DEV_MODE=false                    # Set to true for development
```

### Security Notes

1. **Production Mode** (`DEV_MODE=false`):
   - `ADMIN_PASSWORD` is required
   - All admin endpoints require valid credentials
   - Test endpoint is disabled

2. **Development Mode** (`DEV_MODE=true`):
   - If no `ADMIN_PASSWORD` is set, any credentials are accepted (with warning logs)
   - If `ADMIN_PASSWORD` is set, valid credentials are required
   - Test endpoint is available

## Testing Authentication

### Using curl

```bash
# Test without authentication (should return 401)
curl http://localhost:8000/status

# Test with authentication
curl -u admin:your-password http://localhost:8000/status

# List containers
curl -u admin:your-password http://localhost:8000/containers

# Stop a container
curl -X POST -u admin:your-password http://localhost:8000/container/dev-mycontainer/stop
```

### Using the Test Script

A test script is provided to verify authentication:

```bash
cd packages/webhook
python test_auth.py --username admin --password your-password
```

### Running Unit Tests

```bash
cd packages/webhook
pytest tests/test_authentication.py -v
```

## Migration Guide

If you're upgrading from a version without authentication:

1. Add `ADMIN_PASSWORD` to your `.env` file or environment variables
2. Update any scripts or automation that call admin endpoints to include Basic Auth
3. Consider using a secure password manager or secrets management system for production

## Security Best Practices

1. **Use strong passwords** - Generate a secure random password for production
2. **Use HTTPS** - Always use HTTPS in production to protect credentials in transit
3. **Rotate credentials** - Regularly update the admin password
4. **Limit access** - Restrict network access to admin endpoints where possible
5. **Monitor access** - Review logs for authentication failures and unauthorized access attempts

## Example .env Configuration

```bash
# GitHub webhook configuration
GITHUB_WEBHOOK_SECRET=your-webhook-secret-here
GITHUB_TOKEN=ghp_your-github-token
GITHUB_MENTIONED_USER=your-github-username
CLAUDE_API_KEY=your-claude-api-key

# Admin authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-very-secure-password-here

# Development settings
DEV_MODE=false  # Set to true for development
```