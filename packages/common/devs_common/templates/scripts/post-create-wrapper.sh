#!/bin/bash
set -euo pipefail

echo "🚀 Starting postCreateCommand..."

# Small delay to let bind mounts settle and avoid Node.js EBADF errors
sleep 5
echo "📋 Bind mounts settled, proceeding with setup..."

# Function to run a command with better error reporting
run_step() {
    local step_name="$1"
    local command="$2"
    
    echo "📋 Running $step_name..."
    
    # Capture both stdout and stderr, and exit code
    if output=$(eval "$command" 2>&1); then
        echo "✅ $step_name completed successfully"
        if [ "${DEVS_DEBUG:-}" = "true" ]; then
            echo "🐛 [DEBUG] Output from $step_name:"
            echo "$output"
        fi
        return 0
    else
        exit_code=$?
        echo "❌ $step_name failed with exit code $exit_code"
        echo "📜 Error output:"
        echo "$output"
        return $exit_code
    fi
}

# Run each step with error handling
run_step "setup-vscode-cache" "sudo /usr/local/bin/setup-vscode-cache.sh"
run_step "setup-devs-env.sh" "/usr/local/bin/setup-devs-env.sh"
#run_step "init-firewall.sh" "sudo /usr/local/bin/init-firewall.sh"
run_step "setup-workspace.sh" "/usr/local/bin/setup-workspace.sh"
run_step "start-services.sh" "sudo /usr/local/bin/start-services.sh"

# GitHub auth setup is optional, so handle it separately
echo "📋 Running gh auth setup-git..."
if output=$(gh auth setup-git 2>&1); then
    echo "✅ GitHub auth setup completed"
    if [ "${DEVS_DEBUG:-}" = "true" ]; then
        echo "🐛 [DEBUG] Output from gh auth setup-git:"
        echo "$output"
    fi

else
    echo "⚠️ GitHub auth setup skipped - run 'gh auth login' if needed"
    if [ "${DEVS_DEBUG:-}" = "true" ]; then
        echo "🐛 [DEBUG] gh auth setup-git output:"
        echo "$output"
    fi
fi

echo "🎉 All postCreateCommand steps completed successfully"
