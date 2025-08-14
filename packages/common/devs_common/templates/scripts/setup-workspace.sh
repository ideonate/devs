#!/bin/bash
set -euo pipefail

echo "Setting up development workspace..."

# Enable debug output if DEVS_DEBUG is set
if [ "${DEVS_DEBUG:-}" = "true" ]; then
    echo "🐛 [DEBUG] setup-workspace.sh: Debug mode enabled"
    set -x  # Enable command tracing
fi

# Always use external venv to keep workspace clean
EXTERNAL_VENV_BASE="/home/node/.devs-venv"
echo "📦 Virtual environments will be created at $EXTERNAL_VENV_BASE"
echo "ℹ️  This keeps your workspace directory clean"

# Check if we're in live mode
if [ "${DEVS_LIVE_MODE:-}" = "true" ]; then
    echo "📁 Live mode detected - using host directory directly"
fi


# Function to setup Python virtual environment in a directory
setup_python_env() {
    local dir="$1"
    if [ -d "$dir" ] && [ -f "$dir/requirements.txt" ]; then
        echo "Setting up Python virtual environment for $dir..."
        cd "$dir"
        if [ ! -d "venv" ]; then
            python3 -m venv venv
            echo "Created virtual environment at $dir/venv"
        fi
        
        # Activate and install requirements
        source venv/bin/activate
        pip install --upgrade pip
        
        # Install requirements with SSH key support for private repos
        if [ -f /home/node/.ssh/id_ed25519_github ]; then
            echo "Installing Python dependencies with SSH key support..."
            GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_github -o StrictHostKeyChecking=no" pip install -r requirements.txt
        else
            echo "Installing Python dependencies without SSH key..."
            pip install -r requirements.txt
        fi
        echo "Installed Python dependencies for $dir"
        
        # Install development dependencies if available
        if [ -f "requirements-dev.txt" ]; then
            if [ -f /home/node/.ssh/id_ed25519_github ]; then
                GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_github -o StrictHostKeyChecking=no" pip install -r requirements-dev.txt
            else
                pip install -r requirements-dev.txt
            fi
            echo "Installed development dependencies for $dir"
        fi
        
        # Install pre-commit hooks if .pre-commit-config.yaml exists
        if [ -f ".pre-commit-config.yaml" ]; then
            pre-commit install
            echo "Installed pre-commit hooks for $dir"
        fi
        
        # Create .python-version file pointing to the venv
        venv_path="$(pwd)/venv"
        echo "$venv_path" > .python-version
        echo "Created .python-version file pointing to $venv_path for $dir"
        
        cd ..
    fi
}

# Function to setup Node modules in a directory
setup_node_env() {
    local dir="$1"
    if [ -d "$dir" ] && [ -f "$dir/package.json" ]; then
        echo "Setting up Node modules for $dir..."
        cd "$dir"
        npm install
        echo "Installed Node dependencies for $dir"
        cd ..
    fi
}

# Auto-discover Python projects (any directory with requirements.txt)
echo "Discovering Python projects..."
echo "Current directory: $(pwd)"
echo "Contents: $(ls -la)"


# List all directories
echo "Checking for directories..."
for dirpath in */; do
    if [ -d "$dirpath" ]; then
        dirname=${dirpath%/}
        echo "Found directory: $dirname"
        if [ -f "$dirname/requirements.txt" ]; then
            echo "  -> Has requirements.txt, setting up Python env"
            #setup_python_env "$dirname"
        else
            echo "  -> No requirements.txt found"
        fi
    else
        echo "No directories found with pattern */"
        break
    fi
done

# Also check root directory for requirements.txt
echo "Checking root directory for requirements.txt..."
if [ -f "requirements.txt" ]; then
    echo "Found requirements.txt in root directory, setting up Python virtual environment..."
    
    # Always use external venv location to keep workspace clean
    VENV_DIR="$EXTERNAL_VENV_BASE/workspace-venv"
    mkdir -p "$(dirname "$VENV_DIR")"
    echo "Using venv location: $VENV_DIR"
    
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        echo "Created virtual environment at $VENV_DIR"
    fi
    
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    
    # Install requirements with SSH key support for private repos
    if [ -f /home/node/.ssh/id_ed25519_github ]; then
        echo "Installing Python dependencies with SSH key support..."
        GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_github -o StrictHostKeyChecking=no" pip install -r requirements.txt
    else
        echo "Installing Python dependencies without SSH key..."
        pip install -r requirements.txt
    fi
    echo "Installed Python dependencies in root directory"
    
    if [ -f "requirements-dev.txt" ]; then
        if [ -f /home/node/.ssh/id_ed25519_github ]; then
            GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_github -o StrictHostKeyChecking=no" pip install -r requirements-dev.txt
        else
            pip install -r requirements-dev.txt
        fi
        echo "Installed development dependencies in root directory"
    fi
    
    if [ -f ".pre-commit-config.yaml" ]; then
        pre-commit install
        echo "Installed pre-commit hooks in root directory"
    fi
    
    # Handle potential .python-version file from host
    if [ -f ".python-version" ]; then
        echo "⚠️  Found .python-version file (from host) - this is ignored in the container"
        echo "   The container uses its own Python environment at: $VENV_DIR"
    fi
    
    # Create a symlink to help VS Code discover the Python interpreter
    # This is a well-known location that the Python extension checks
    if [ ! -e "$HOME/.python_venv" ]; then
        ln -s "$VENV_DIR" "$HOME/.python_venv"
        echo "Created symlink at ~/.python_venv for VS Code Python discovery"
    fi
    
    echo "✅ Python environment ready at: $VENV_DIR"
    echo "   To activate: source $VENV_DIR/bin/activate"
    
    # Always create VS Code settings for the external venv
    if [ -d ".vscode" ] || [ -f *.code-workspace 2>/dev/null ]; then
        mkdir -p .vscode
        # Create or update settings for the container
        cat > .vscode/settings.devcontainer.json << EOF
{
    "python.defaultInterpreterPath": "$VENV_DIR/bin/python",
    "python.terminal.activateEnvironment": true
}
EOF
        echo "Created .vscode/settings.devcontainer.json for VS Code Python extension"
    fi
else
    echo "No requirements.txt found in root directory"
fi

# Auto-discover Node projects (any directory with package.json)
echo "Discovering Node projects..."
for dirpath in */; do
    if [ -d "$dirpath" ]; then
        dirname=${dirpath%/}
        echo "Checking directory: $dirname"
        if [ -f "$dirname/package.json" ]; then
            echo "  -> Has package.json, setting up Node env"
            #setup_node_env "$dirname"
        else
            echo "  -> No package.json found"
        fi
    else
        echo "No directories found for Node projects"
        break
    fi
done

# Also check root directory for package.json
echo "Checking root directory for package.json..."
if [ -f "package.json" ]; then
    echo "Found package.json in root directory, setting up Node modules..."
    npm install
    echo "Installed Node dependencies in root directory"
else
    echo "No package.json found in root directory"
fi

echo "Workspace setup complete!"
echo ""
echo "Discovered environments:"

# Show discovered Python environments
# Check root directory first
if [ -f "./requirements.txt" ] || [ -f "./package.json" ]; then
    if [ -f "./requirements.txt" ]; then
        echo "  Python (root): source $EXTERNAL_VENV_BASE/workspace-venv/bin/activate"
    fi
    if [ -f "./package.json" ]; then
        echo "  Node (root): npm run dev (or check package.json scripts)"
    fi
fi

# Check subdirectories
if [ -d * ] 2>/dev/null; then
    for dirpath in */; do
        dirname=${dirpath%/}  # Remove trailing slash
        if [ -d "$dirname" ]; then
            if [ -f "$dirname/requirements.txt" ]; then
                echo "  Python ($dirname): cd $dirname && source venv/bin/activate"
            fi
            if [ -f "$dirname/package.json" ]; then
                echo "  Node ($dirname): cd $dirname && npm run dev (or check package.json scripts)"
            fi
        fi
    done
fi