# Systemd Service Setup for devs-webhook

This directory contains the systemd service configuration and setup script for running the devs-webhook server as a system service on Ubuntu/Debian systems.

## Quick Start

For your specific use case (user `dan`, working directory `~/Dev/devs`):

```bash
cd packages/webhook/systemd
./setup-systemd.sh --user dan --working-dir /home/dan/Dev/devs --env-file /home/dan/Dev/devs/.env
```

## Prerequisites

1. **Python 3.8+** installed
2. **devs-webhook** package installed:
   ```bash
   cd packages/webhook
   pip install -e .
   ```
3. **Docker** installed and the user added to the docker group:
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in for group changes to take effect
   ```
4. **Dependencies** installed (gh CLI, devcontainer CLI, etc.)
5. **Environment file** (`.env`) with required configuration

## Files

- `devs-webhook.service` - Systemd service template
- `setup-systemd.sh` - Interactive setup script
- `README.md` - This documentation

## Setup Instructions

### 1. Automatic Setup (Recommended)

Use the provided setup script:

```bash
./setup-systemd.sh --user <username> --working-dir <path> --env-file <path>
```

Options:
- `--user` - User to run the service as (default: current user)
- `--group` - Group to run the service as (default: current user) 
- `--working-dir` - Working directory for the service (default: current directory)
- `--env-file` - Path to .env file (required)
- `--python-path` - Path to Python executable (default: system python3)

Example:
```bash
./setup-systemd.sh --user dan --working-dir /home/dan/Dev/devs --env-file /home/dan/Dev/devs/.env
```

### 2. Manual Setup

If you prefer manual setup:

1. Copy and edit the service file:
   ```bash
   sudo cp devs-webhook.service /etc/systemd/system/
   sudo nano /etc/systemd/system/devs-webhook.service
   ```

2. Replace the placeholders:
   - `%USER%` → Your username (e.g., `dan`)
   - `%GROUP%` → Your group (e.g., `dan`)
   - `%WORKING_DIR%` → Your working directory (e.g., `/home/dan/Dev/devs`)
   - `%ENV_FILE%` → Path to your .env file (e.g., `/home/dan/Dev/devs/.env`)
   - `%PYTHON_PATH%` → Path to Python (e.g., `/usr/bin/python3`)

3. Reload systemd and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable devs-webhook
   sudo systemctl start devs-webhook
   ```

## Service Management

Once installed, manage the service with standard systemctl commands:

```bash
# Start the service
sudo systemctl start devs-webhook

# Stop the service
sudo systemctl stop devs-webhook

# Restart the service
sudo systemctl restart devs-webhook

# Check service status
sudo systemctl status devs-webhook

# Enable auto-start on boot
sudo systemctl enable devs-webhook

# Disable auto-start on boot
sudo systemctl disable devs-webhook

# View logs
sudo journalctl -u devs-webhook -f
```

## Environment File (.env)

The service requires an environment file with the following variables:

```bash
# Required
GITHUB_WEBHOOK_SECRET=your-webhook-secret
GITHUB_TOKEN=your-github-token
GITHUB_MENTIONED_USER=username-to-watch
CLAUDE_API_KEY=your-claude-api-key

# Optional
CONTAINER_POOL=devs-webhook-1,devs-webhook-2
CONTAINER_TIMEOUT_MINUTES=60
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
LOG_LEVEL=INFO
```

## Security Notes

The systemd service includes several security hardening options:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolates /tmp directory
- `ProtectSystem=strict` - Makes system directories read-only
- `ProtectHome=read-only` - Makes home directories read-only
- `ReadWritePaths` - Explicitly allows write access only to necessary directories
- `MemoryLimit=2G` - Limits memory usage
- `CPUQuota=200%` - Limits CPU usage to 2 cores

## Troubleshooting

### Service won't start

1. Check the logs:
   ```bash
   sudo journalctl -u devs-webhook -n 50
   ```

2. Verify the environment file exists and is readable:
   ```bash
   ls -la /path/to/.env
   ```

3. Check Python is installed and accessible:
   ```bash
   which python3
   python3 --version
   ```

4. Ensure the user has necessary permissions:
   - Member of docker group
   - Can read the .env file
   - Can write to working directory

### Permission errors

If you see permission errors, ensure:

1. User is in docker group:
   ```bash
   groups username | grep docker
   ```

2. Working directory permissions:
   ```bash
   ls -ld /path/to/working/dir
   ```

3. .env file permissions:
   ```bash
   chmod 600 /path/to/.env
   chown username:group /path/to/.env
   ```

### Port already in use

If port 8000 is already in use, update the .env file:
```bash
WEBHOOK_PORT=8001
```

Then restart the service:
```bash
sudo systemctl restart devs-webhook
```

## Monitoring

Monitor the service health:

```bash
# Check if service is running
systemctl is-active devs-webhook

# View recent logs
sudo journalctl -u devs-webhook --since "1 hour ago"

# Check webhook handler status
curl http://localhost:8000/status
```

## Uninstalling

To remove the service:

```bash
# Stop and disable the service
sudo systemctl stop devs-webhook
sudo systemctl disable devs-webhook

# Remove the service file
sudo rm /etc/systemd/system/devs-webhook.service

# Reload systemd
sudo systemctl daemon-reload
```