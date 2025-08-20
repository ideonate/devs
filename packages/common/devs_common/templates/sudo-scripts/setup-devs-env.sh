#!/bin/bash
set -euo pipefail

echo "Setting up devs environment configuration..."

# Enable debug output if DEVS_DEBUG is set
if [ "${DEVS_DEBUG:-}" = "true" ]; then
    echo "🐛 [DEBUG] setup-devs-env.sh: Debug mode enabled"
    # Note: We don't use 'set -x' here to avoid exposing sensitive tokens
    # in the command tracing output
fi

# Check SSH setup (configured during Docker build)
check_ssh_setup() {
    if [ -d /home/node/.ssh ] && [ "$(ls -A /home/node/.ssh 2>/dev/null)" ]; then
        echo "✅ SSH keys found and configured during build"
        if [ -f /home/node/.ssh/id_ed25519_github ] || [ -f /home/node/.ssh/id_rsa_github ]; then
            echo "✅ GitHub SSH key detected - private repositories should work"
        fi
    else
        echo "ℹ️  No SSH keys configured"
        echo "   To enable SSH access (including private repositories):"
        echo "   1. Create directory: .devcontainer/.ssh"
        echo "   2. Copy your SSH keys there (e.g., id_ed25519_github)"
        echo "   3. Rebuild the devcontainer"
    fi
}

# Check GitHub token setup (configured via mounted env files)
check_github_token_setup() {
    local gh_token=""
    
    # First, try to load from mounted env files
    if [ -f /home/node/.devs-env/.env ]; then
        echo "✅ Found mounted env file at /home/node/.devs-env/.env"
        # Source the env file to load variables
        set -a  # automatically export all variables
        source /home/node/.devs-env/.env
        set +a  # stop auto-exporting
        
        # Get GH_TOKEN from the sourced env file
        gh_token="${GH_TOKEN:-}"
    fi
    
    # If not found in mounted env, fall back to environment variable
    if [ -z "$gh_token" ]; then
        gh_token="${GH_TOKEN:-}"
    fi
    
    if [ -n "$gh_token" ]; then
        echo "✅ GitHub token (GH_TOKEN) is available"
        
        # Export it for this session
        export GH_TOKEN="$gh_token"
        
        # Configure git user info if provided in env file
        if [ -n "${GH_USER_NAME:-}" ]; then
            git config --global user.name "$GH_USER_NAME"
            echo "✅ Git user.name set to: $GH_USER_NAME"
        fi
        
        if [ -n "${GH_USER_EMAIL:-}" ]; then
            git config --global user.email "$GH_USER_EMAIL"
            echo "✅ Git user.email set to: $GH_USER_EMAIL"
        fi
        
        # Set git to not trust ctime to avoid confusion with host timezone differences
        git config --global core.trustctime false
        echo "✅ Git core.trustctime set to false (prevents timezone-related rebase issues)"
        
        # Ensure it's available in all shell sessions for the node user
        if ! grep -q "source /home/node/.devs-env/.env" /home/node/.zshrc 2>/dev/null; then
            echo "# Load devs environment variables" >> /home/node/.zshrc
            echo "if [ -f /home/node/.devs-env/.env ]; then" >> /home/node/.zshrc
            echo "    set -a" >> /home/node/.zshrc
            echo "    source /home/node/.devs-env/.env" >> /home/node/.zshrc
            echo "    set +a" >> /home/node/.zshrc
            echo "fi" >> /home/node/.zshrc
        fi
        if ! grep -q "source /home/node/.devs-env/.env" /home/node/.bashrc 2>/dev/null; then
            echo "# Load devs environment variables" >> /home/node/.bashrc
            echo "if [ -f /home/node/.devs-env/.env ]; then" >> /home/node/.bashrc
            echo "    set -a" >> /home/node/.bashrc
            echo "    source /home/node/.devs-env/.env" >> /home/node/.bashrc
            echo "    set +a" >> /home/node/.bashrc
            echo "fi" >> /home/node/.bashrc
        fi
        
        # Test if gh CLI can authenticate
        if command -v gh >/dev/null 2>&1; then
            if gh auth status >/dev/null 2>&1; then
                echo "✅ GitHub CLI authentication is working"
            else
                echo "ℹ️  GitHub CLI token available but not yet configured"
                echo "   Run 'gh auth setup-git' to complete setup"
            fi
        fi
    else
        echo "ℹ️  No GitHub token (GH_TOKEN) configured"
        echo "   To enable GitHub API access:"
        echo "   1. Create ~/.devs/envs/<project-name>/.env with GH_TOKEN=your_token"
        echo "   2. Or set environment variable: export GH_TOKEN=your_token_here"
        echo "   3. Restart the devcontainer"
    fi
}

# Check SSH access (configured during build)
check_ssh_setup

# Check GitHub token access (configured via mounted env files)
check_github_token_setup

echo "Devs environment setup complete!"