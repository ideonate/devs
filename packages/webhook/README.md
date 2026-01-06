# devs-webhook - GitHub Webhook Handler

A GitHub webhook handler that automatically responds to @mentions in issues and pull requests using Claude Code to analyze and solve problems in devcontainers.

## Features

- **Smart @mention Detection**: Responds when a configured user is @mentioned in GitHub issues/PRs
- **Multiple Task Sources**: Support for direct webhook reception (FastAPI) or polling from AWS SQS queues
- **Container Pool Management**: Manages a pool of named devcontainers (eamonn, harry, darren by default)
- **Claude Code Integration**: Uses Claude Code SDK to analyze issues and implement solutions
- **GitHub Checks API CI**: Automated test execution on push/PR events with status reporting
- **Environment Variable Management**: Layered DEVS.yml configuration with user-specific overrides
- **Repository Management**: Automatically clones and caches GitHub repositories
- **Automated Responses**: Creates pull requests, commits changes, and comments back on issues
- **Scalable Architecture**: Deploy as a single server or scale horizontally with SQS-based worker pools

## Quick Start

### Installation

```bash
# Install the webhook package
cd packages/webhook
pip install -e .

# Or install from the monorepo root
pip install -e packages/webhook/
```

### Configuration

Set up environment variables:

```bash
# Required settings
export GITHUB_WEBHOOK_SECRET="your-webhook-secret"
export GITHUB_TOKEN="ghp_your-github-token"
export GITHUB_MENTIONED_USER="your-github-username"
export CLAUDE_API_KEY="your-claude-api-key"

# Admin authentication (required for production)
export ADMIN_USERNAME="admin"  # Default: admin
export ADMIN_PASSWORD="your-secure-password"  # Required in production

# Access control settings
export ALLOWED_ORGS="myorg,anotherorg"  # GitHub orgs allowed to use webhook
export ALLOWED_USERS="user1,user2"       # GitHub users allowed to use webhook
export AUTHORIZED_TRIGGER_USERS="danlester,admin"  # Users who can trigger processing

# Optional settings (with defaults)
export CONTAINER_POOL="eamonn,harry,darren"
export CONTAINER_TIMEOUT_MINUTES="30"
export MAX_CONCURRENT_TASKS="3"
export WEBHOOK_HOST="0.0.0.0"
export WEBHOOK_PORT="8000"
```

### Start the Server

```bash
# Start webhook server (default mode)
devs-webhook serve

# Or with custom options
devs-webhook serve --host 127.0.0.1 --port 8080 --reload

# Start in SQS polling mode for scalable deployments
export TASK_SOURCE=sqs
export AWS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/123456789/devs-webhook-queue"
devs-webhook serve --source sqs
```

## Deployment Options

### Webhook Mode (Default)

Direct webhook reception using FastAPI. Suitable for:
- Simple VPS deployments
- Single-server setups
- Low to moderate traffic

```bash
# GitHub Webhook → devs-webhook server (FastAPI) → Container Pool
export TASK_SOURCE=webhook  # or omit (default)
devs-webhook serve
```

### SQS Mode (Scalable)

Decoupled architecture using AWS SQS. Suitable for:
- High-traffic scenarios
- Multiple worker instances
- Better fault tolerance and retry logic

```bash
# GitHub Webhook → Lambda/API Gateway → SQS Queue → devs-webhook workers
export TASK_SOURCE=sqs
export AWS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/..."
devs-webhook serve --source sqs
```

#### Burst Mode

For batch processing or scheduled jobs, use `--burst` to process all available messages and exit:

```bash
# Process all messages in queue then exit
devs-webhook serve --source sqs --burst
```

Exit codes:
- **0**: Successfully processed one or more messages
- **42**: Queue was empty (no messages to process)
- **Other**: Error occurred

This is useful for:
- Scheduled cron jobs that drain the queue periodically
- Lambda-triggered batch processing
- Testing and debugging SQS integration

**Security**: Both modes validate GitHub webhook signatures for defense-in-depth security.

For detailed configuration and deployment guides, see:
- [Task Sources Documentation](docs/TASK_SOURCES.md) - Complete guide to webhook vs SQS modes
- [Lambda Example](examples/sqs_webhook_forwarder.py) - Example Lambda function for SQS forwarding

## How It Works

1. **GitHub Webhook**: Receives webhook events from GitHub when issues/PRs are created or commented on
2. **@mention Detection**: Checks if the configured user is @mentioned in the content
3. **Container Allocation**: Allocates an available container from the pool (eamonn, harry, darren)
4. **Repository Setup**: Clones/updates the repository and sets up the devcontainer workspace
5. **Claude Code Execution**: Uses Claude Code SDK to analyze the issue and implement solutions
6. **Automated Response**: Comments back on the issue/PR with results, creates PRs if needed

## Usage Examples

### Basic Issue Resolution

Create a GitHub issue:

```
There's a bug in the user authentication system where passwords aren't being validated properly.

@your-username can you take a look at this?
```

The webhook will:

1. Detect the @mention
2. Allocate a container
3. Clone the repository
4. Use Claude Code to analyze the auth system
5. Implement a fix
6. Create a pull request
7. Comment back with the solution

### Feature Requests

Create an issue:

```
Can we add a dark mode toggle to the settings page?

@your-username please implement this feature.
```

Claude Code will:

1. Analyze the current UI structure
2. Implement the dark mode functionality
3. Create appropriate tests
4. Submit a pull request
5. Update the original issue

## Container Pool

The webhook manages a pool of named containers:

- **eamonn**: First container in rotation
- **harry**: Second container in rotation
- **darren**: Third container in rotation

Each container:

- Gets a fresh workspace copy of the repository
- Has a 30-minute timeout (configurable)
- Is automatically cleaned up after use
- Can handle one task at a time

## CLI Commands

```bash
# Start the webhook server
devs-webhook serve

# Check server status
devs-webhook status

# View configuration
devs-webhook config

# Stop a specific container
devs-webhook stop-container eamonn

# Test setup and dependencies
devs-webhook test-setup
```

## API Endpoints

- `POST /webhook` - GitHub webhook endpoint
- `GET /health` - Health check
- `GET /status` - Detailed status information
- `GET /containers` - List container status
- `POST /container/{name}/stop` - Stop specific container

## GitHub Webhook Setup

1. Go to your repository Settings → Webhooks
2. Add webhook with URL: `https://your-domain.com/webhook`
3. Set Content Type: `application/json`
4. Set Secret: Use your `GITHUB_WEBHOOK_SECRET`
5. Select events: Issues, Pull requests, Issue comments, Pull request reviews

## Dependencies

- **Python 3.8+**: Runtime environment
- **Docker**: Container management
- **GitHub CLI**: `gh` command for GitHub operations
- **DevContainer CLI**: `devcontainer` command for container operations
- **Claude API Key**: For Claude Code SDK access

## Architecture

```
GitHub → Webhook → FastAPI → Container Pool → Claude Code → GitHub Response
   ↓        ↓         ↓           ↓              ↓            ↓
Issue    Parse     Allocate    Clone Repo    Analyze &      Comment/PR
Created  Event     Container   & Setup       Solve Issue    Back
```

### Key Components

- **WebhookHandler**: Main orchestrator
- **ContainerPool**: Manages eamonn/harry/darren containers
- **RepositoryManager**: Clones and caches repositories
- **ClaudeDispatcher**: Executes tasks with Claude Code SDK
- **GitHubClient**: Handles GitHub API operations

## Configuration

### Repository Configuration (DEVS.yml)

Repositories can include a `DEVS.yml` file in their root directory to customize how the webhook handler interacts with them:

```yaml
# DEVS.yml - Repository-specific configuration
default_branch: develop  # Default branch name (default: main)
prompt_extra: |          # Additional instructions for Claude
  This project uses a specific code style:
  - Always use tabs for indentation
  - Keep functions under 50 lines
  - Add JSDoc comments to all public functions
direct_commit: true      # Commit directly to default branch instead of creating PRs
single_queue: true       # Process all events for this repo sequentially in same container
prompt_override: |       # Complete replacement for the default prompt (optional)
  Custom prompt template here...
  Available variables: {event_type}, {event_type_full}, {task_description},
  {repo_name}, {workspace_path}, {github_username}
ci_enabled: true         # Enable CI mode for push/PR events
ci_test_command: npm test # Command to run for CI tests
ci_branches:             # Branches to run CI on
  - main
  - develop

env_vars:                # Environment variables for containers
  default:               # Default values for all containers
    NODE_ENV: production
    API_URL: https://api.example.com
    DEBUG: "false"
  
  eamonn:                # Container-specific overrides
    DEBUG: "true"
    EAMONN_SPECIAL: "enabled"
    
  harry:
    NODE_ENV: staging
    API_URL: https://staging-api.example.com
```

Available options:

- **`default_branch`**: The main branch name for the repository (e.g., `main`, `master`, `develop`)
  - Used when pulling latest changes before starting work
  - Default: `main`
  
- **`prompt_extra`**: Additional instructions appended to Claude's prompt
  - Use for project-specific guidelines, coding standards, or constraints
  - Can be multi-line using YAML's `|` syntax
  - Default: empty string

- **`direct_commit`**: Whether to commit directly to the default branch
  - When `true`, Claude will commit directly to the default branch instead of creating PRs
  - When `false`, Claude will create feature branches and pull requests (default behavior)
  - Only creates PRs if there would be merge conflicts
  - Default: `false`

- **`single_queue`**: Process all events for this repository sequentially
  - When `true`, all webhook events for this repository are processed by the same container in order
  - Prevents conflicts when multiple events would modify the same files
  - Useful for repositories where strict ordering is important
  - Default: `false` (events can be processed in parallel by different containers)

- **`prompt_override`**: Complete replacement for the default prompt (advanced)
  - Allows full customization of Claude's instructions
  - Use Python string formatting with available variables
  - Variables: `{event_type}`, `{event_type_full}`, `{task_description}`, `{repo_name}`, `{workspace_path}`, `{github_username}`
  - Takes precedence over all other prompt settings
  - Default: not set (uses standard prompt)

- **`ci_enabled`**: Enable continuous integration mode
  - When `true`, webhook responds to push and PR events by running tests
  - Tests are executed in containers and results reported via GitHub Checks API
  - Default: `false`

- **`ci_test_command`**: Command to run for CI tests
  - Shell command executed in container for CI test runs
  - Should exit with code 0 for success, non-zero for failure
  - Default: `./runtests.sh`

- **`ci_branches`**: Branches to run CI on for push events
  - List of branch names to trigger CI for push events
  - PR events always trigger CI regardless of target branch
  - Default: `["main", "master"]`

- **`env_vars`**: Environment variables for containers
  - Supports `default` section for all containers and container-specific overrides
  - Container-specific variables override defaults
  - User-specific overrides can be configured via `~/.devs/envs/{org-repo}/DEVS.yml`
  - Variables are passed to container during startup
  - Default: empty

### User-Specific Configuration

Users can override repository settings with their own DEVS.yml files:

```bash
# Global defaults for all projects
mkdir -p ~/.devs/envs/default
cat > ~/.devs/envs/default/DEVS.yml << 'EOF'
env_vars:
  default:
    GLOBAL_SETTING: "user_preference"
    MY_SECRET: "user_secret"
EOF

# Project-specific overrides (org-repo format)
mkdir -p ~/.devs/envs/myorg-myrepo
cat > ~/.devs/envs/myorg-myrepo/DEVS.yml << 'EOF'
env_vars:
  eamonn:
    DEBUG: "true"
    LOCAL_SECRET: "dev_secret"
ci_enabled: true
ci_test_command: "npm run test:full"
EOF
```

**Priority order for configuration:**
1. `~/.devs/envs/{org-repo}/DEVS.yml` (user-specific project overrides)
2. `~/.devs/envs/default/DEVS.yml` (user defaults)
3. `{repo-root}/DEVS.yml` (repository configuration)

📖 **[See ../../example-usage.md for detailed examples and scenarios](../../example-usage.md)**

The webhook handler automatically detects and uses these settings when processing tasks for the repository.

### Environment Variables

| Variable                    | Default                      | Description                              |
| --------------------------- | ---------------------------- | ---------------------------------------- |
| `GITHUB_WEBHOOK_SECRET`     | Required                     | GitHub webhook secret                    |
| `GITHUB_TOKEN`              | Required                     | GitHub personal access token             |
| `GITHUB_MENTIONED_USER`     | Required                     | Username to watch for @mentions          |
| `CLAUDE_API_KEY`            | Required                     | Claude API key                           |
| `ALLOWED_ORGS`              | (empty)                      | Comma-separated list of allowed GitHub orgs |
| `ALLOWED_USERS`             | (empty)                      | Comma-separated list of allowed GitHub users |
| `AUTHORIZED_TRIGGER_USERS`  | (empty - allows all)         | Comma-separated list of users who can trigger events |
| `CONTAINER_POOL`            | `eamonn,harry,darren`        | Container names                          |
| `CONTAINER_TIMEOUT_MINUTES` | `30`                         | Container timeout                        |
| `MAX_CONCURRENT_TASKS`      | `3`                          | Max parallel tasks                       |
| `REPO_CACHE_DIR`            | `~/.devs-webhook/repos`      | Repository cache                         |
| `WORKSPACE_DIR`             | `~/.devs-webhook/workspaces` | Container workspaces                     |
| `WEBHOOK_HOST`              | `0.0.0.0`                    | Server host                              |
| `WEBHOOK_PORT`              | `8000`                       | Server port                              |

### S3 Artifact Upload (Optional)

Upload test artifacts (bridge directory contents) to S3 after CI runs. Useful for sharing test results, logs, or generated files.

| Variable                    | Default           | Description                              |
| --------------------------- | ----------------- | ---------------------------------------- |
| `AWS_S3_ARTIFACT_BUCKET`    | (empty)           | S3 bucket name (enables feature when set)|
| `AWS_S3_ARTIFACT_PREFIX`    | `devs-artifacts`  | S3 key prefix for artifacts              |
| `AWS_S3_ARTIFACT_BASE_URL`  | (empty)           | Public URL base (e.g., CloudFront URL)   |
| `AWS_REGION`                | `us-east-1`       | AWS region for S3 operations             |

**How it works:**
- Test scripts write files to the bridge mount folder (available as `$BRIDGE_DIR` in containers)
- After test execution, the bridge directory is tarred and uploaded to S3
- S3 paths include a secret token for secure sharing: `{prefix}/{repo}/{type}/{secret}/{timestamp}.tar.gz`
- If `AWS_S3_ARTIFACT_BASE_URL` is set, a public URL is included in GitHub Check results

**Example configuration:**
```bash
export AWS_S3_ARTIFACT_BUCKET=my-artifacts-bucket
export AWS_S3_ARTIFACT_BASE_URL=https://d1234567890.cloudfront.net
```

**Note:** Requires `boto3` (`pip install boto3`) and appropriate AWS credentials.

### GitHub App Authentication (Optional)

For enhanced GitHub Checks API support, you can optionally configure GitHub App authentication. This provides better permissions and rate limits for API operations, especially when using the Checks API to report test results.

#### When to Use GitHub App Authentication

- **Enhanced Checks API**: GitHub Apps have better permissions for creating and updating check runs
- **Better Rate Limits**: GitHub Apps get higher API rate limits
- **Organization Repositories**: Required for some organization-level permissions
- **Better Security**: App-based authentication is more secure than personal tokens

If GitHub App authentication is not configured, the webhook will fall back to personal token authentication.

#### Setting Up a GitHub App

1. **Create a GitHub App**:
   - Go to GitHub Settings → Developer settings → GitHub Apps
   - Click "New GitHub App"
   - Fill in the app details:
     - **App name**: `devs-webhook-your-org`
     - **Homepage URL**: Your webhook server URL
     - **Webhook URL**: `https://your-domain.com/webhook`
     - **Webhook secret**: Use your `GITHUB_WEBHOOK_SECRET`

2. **Configure Permissions**:
   - **Repository permissions**:
     - Contents: Read & Write
     - Issues: Read & Write
     - Pull requests: Read & Write
     - Checks: Write
     - Metadata: Read
   - **Subscribe to events**:
     - Issues
     - Pull request
     - Issue comments
     - Pull request reviews
     - Push (for CI features)

3. **Generate Private Key**:
   - In the app settings, scroll down to "Private keys"
   - Click "Generate a private key"
   - Download the `.pem` file

4. **Install the App**:
   - Go to the app's public page or your organization/account settings
   - Install the app on the repositories you want to use
   - Note the installation ID from the URL (e.g., `/installations/12345`)

#### Configuration

Add these environment variables to enable GitHub App authentication:

```bash
# GitHub App authentication (optional)
export GITHUB_APP_ID="123456"
export GITHUB_APP_PRIVATE_KEY="/path/to/private-key.pem"
export GITHUB_APP_INSTALLATION_ID="12345"  # Optional, can be auto-discovered

# Or provide private key content directly
export GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"
```

#### Environment Variables for GitHub App

| Variable                    | Default      | Description                              |
| --------------------------- | ------------ | ---------------------------------------- |
| `GITHUB_APP_ID`            | (empty)      | GitHub App ID (e.g., 123456)            |
| `GITHUB_APP_PRIVATE_KEY`   | (empty)      | Private key content or path to .pem file |
| `GITHUB_APP_INSTALLATION_ID` | (empty)    | Installation ID (auto-discovered if empty) |

#### How It Works

When GitHub App authentication is configured:

1. **Checks API Operations**: The webhook will use GitHub App authentication for creating and updating check runs, providing better permissions and reliability
2. **Fallback Behavior**: If GitHub App authentication fails, the webhook automatically falls back to personal token authentication  
3. **Auto-Discovery**: If `GITHUB_APP_INSTALLATION_ID` is not provided, the webhook will automatically discover the installation ID for each repository
4. **Selective Usage**: GitHub App auth is only used when beneficial (like Checks API), while other operations may still use personal tokens

#### Troubleshooting GitHub App Setup

- **"Installation not found"**: Ensure the app is installed on the repository
- **"Invalid private key"**: Verify the private key format and content
- **"Permission denied"**: Check the app has required permissions (Contents, Issues, Pull requests, Checks)
- **"App authentication failed"**: Verify the App ID and private key are correct

## Deployment

### Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Set environment variables
export GITHUB_WEBHOOK_SECRET="dev-secret"
# ... other vars

# Start with reload
devs-webhook serve --reload
```

### Local Testing

The webhook server provides test endpoints for local development that simulate GitHub webhook events without requiring actual GitHub webhooks.

**1. Start the server in development mode:**

```bash
# Load environment variables and start server
set -a; source ./packages/webhook/.env; set +a
devs-webhook serve --env-file ./packages/webhook/.env --dev --port 8001
```

**2. Test Claude/issue handling (`/testevent`):**

```bash
# Load env vars for authentication
set -a; source ./packages/webhook/.env; set +a

# Send a test prompt (simulates @mention in an issue)
devs-webhook test --repo myorg/myproject --port 8001 "Fix the login bug"
```

**3. Test CI/runtests handling (`/testruntests`):**

```bash
# Load env vars for authentication
set -a; source ./packages/webhook/.env; set +a

# Send a test CI event (simulates a push event, skips GitHub Checks API)
devs-webhook test-runtests --repo myorg/myproject --port 8001 --branch main
devs-webhook test-runtests --repo myorg/myproject --port 8001 --branch feature-branch --commit abc123
```

**Test command options:**

| Option | Description |
|--------|-------------|
| `--repo` | Repository name in org/repo format |
| `--port` | Webhook server port (default: 8000) |
| `--host` | Webhook server host (default: 127.0.0.1) |
| `--username` | Admin username for auth (default: from `ADMIN_USERNAME` env var) |
| `--password` | Admin password for auth (default: from `ADMIN_PASSWORD` env var) |
| `--branch` | Branch to test (test-runtests only, default: main) |
| `--commit` | Commit SHA to test (test-runtests only, default: HEAD) |

**Note:** The test endpoints are only available when the server is started with `--dev` flag. Test events skip GitHub API calls (no check runs created, no comments posted).

### Production with Docker

```bash
# Build image
docker build -t devs-webhook .

# Run container
docker run -d \
  --name devs-webhook \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e GITHUB_WEBHOOK_SECRET="your-secret" \
  -e GITHUB_TOKEN="your-token" \
  -e GITHUB_MENTIONED_USER="your-username" \
  -e CLAUDE_API_KEY="your-key" \
  devs-webhook
```

### Semi-permanent with nohup

```bash
# Start in background
nohup devs-webhook serve &

# View logs
tail -f nohup.out

# Find and kill the process
ps aux | grep devs-webhook
kill <PID>
```

### Production with Systemd (Ubuntu/Debian)

For running as a system service on Ubuntu:

```bash
# Install the webhook package
pip install -e packages/webhook/

# Use the systemd setup script
cd packages/webhook/systemd
./setup-systemd.sh --user dan --working-dir /home/dan/Dev/devs --env-file /home/dan/Dev/devs/.env

# Manage the service
sudo systemctl start devs-webhook    # Start service
sudo systemctl status devs-webhook   # Check status
sudo journalctl -u devs-webhook -f   # View logs
```

See [`systemd/README.md`](systemd/README.md) for detailed systemd setup instructions.

## Security

### Access Control

The webhook handler implements multiple layers of access control:

1. **Authorized Trigger Users** (`AUTHORIZED_TRIGGER_USERS`):
   - Only users in this list can trigger webhook processing
   - If empty, all users are allowed (backward compatibility)
   - Prevents unauthorized users from triggering actions
   - Example: `AUTHORIZED_TRIGGER_USERS="danlester,teamlead"`

2. **Repository Allowlist** (`ALLOWED_ORGS` and `ALLOWED_USERS`):
   - Restricts which repositories can use the webhook
   - Checks repository owner against allowed organizations and users
   - Both settings work together (any match allows access)
   - Example: `ALLOWED_ORGS="mycompany"` and `ALLOWED_USERS="trusted-user"`

3. **@mention Detection** (`GITHUB_MENTIONED_USER`):
   - Only processes events where the configured user is @mentioned
   - Prevents accidental or unwanted processing

### Other Security Features

- **Webhook Signatures**: All webhooks are verified using HMAC signatures
- **Token Scope**: GitHub token should have minimal required permissions
- **Container Isolation**: Each task runs in an isolated devcontainer
- **Timeout Protection**: Containers automatically timeout and cleanup

## Troubleshooting

### Common Issues

1. **"No containers available"**: All containers are busy, wait or increase pool size
2. **"Repository clone failed"**: Check GitHub token permissions
3. **"Claude Code execution failed"**: Check Claude API key and model availability
4. **"Invalid webhook signature"**: Verify webhook secret matches

### Debugging

```bash
# Check configuration
devs-webhook config

# View server status
devs-webhook status

# Test dependencies
devs-webhook test-setup

# Check logs (when running with structured logging)
tail -f /var/log/devs-webhook.log
```

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black devs_webhook tests

# Type checking
mypy devs_webhook
```

## License

MIT License - see the main repository for details.
