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

# Function to install a Python package from pyproject.toml in editable mode
install_pyproject_package() {
    local pkg_dir="$1"
    local extras="${2:-dev}"  # Default to [dev] extras

    if [ ! -f "$pkg_dir/pyproject.toml" ]; then
        return 1
    fi

    echo "📦 Installing $pkg_dir in editable mode with [$extras] extras..."

    if [ -f /home/node/.ssh/id_ed25519_github ]; then
        GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_github -o StrictHostKeyChecking=no" \
            pip install -e "$pkg_dir[$extras]"
    else
        pip install -e "$pkg_dir[$extras]"
    fi

    echo "✅ Installed $pkg_dir"
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

# Setup Python virtual environment
echo "Setting up Python virtual environment..."

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

# Check for monorepo structure with packages/ directory containing pyproject.toml files
PYTHON_INSTALLED=false
if [ -d "packages" ]; then
    echo "Detected packages/ directory - checking for Python monorepo structure..."

    # Count packages with pyproject.toml
    PKG_COUNT=0
    for pkg_dir in packages/*/; do
        if [ -f "${pkg_dir}pyproject.toml" ]; then
            PKG_COUNT=$((PKG_COUNT + 1))
        fi
    done

    if [ "$PKG_COUNT" -gt 0 ]; then
        echo "Found $PKG_COUNT Python packages in packages/ directory"
        PYTHON_INSTALLED=true

        # Install common package first (if it exists) since other packages depend on it
        if [ -f "packages/common/pyproject.toml" ]; then
            install_pyproject_package "packages/common" "dev"
        fi

        # Install remaining packages in editable mode with dev dependencies
        for pkg_dir in packages/*/; do
            pkg_name="${pkg_dir%/}"
            # Skip common since we already installed it
            if [ "$pkg_name" = "packages/common" ]; then
                continue
            fi
            if [ -f "${pkg_dir}pyproject.toml" ]; then
                install_pyproject_package "$pkg_name" "dev"
            fi
        done

        echo "✅ All monorepo packages installed in editable mode"
    fi
fi

# Check for root pyproject.toml (single package project)
if [ "$PYTHON_INSTALLED" = "false" ] && [ -f "pyproject.toml" ]; then
    echo "Found pyproject.toml in root directory..."
    PYTHON_INSTALLED=true
    install_pyproject_package "." "dev"
fi

# Fall back to requirements.txt if no pyproject.toml found
if [ "$PYTHON_INSTALLED" = "false" ] && [ -f "requirements.txt" ]; then
    echo "Found requirements.txt in root directory, installing dependencies..."
    PYTHON_INSTALLED=true

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
fi

# Common post-install tasks for Python projects
if [ "$PYTHON_INSTALLED" = "true" ]; then
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
    echo "No Python project detected (no pyproject.toml or requirements.txt found)"
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
if [ "$PYTHON_INSTALLED" = "true" ]; then
    echo "  Python: source $EXTERNAL_VENV_BASE/workspace-venv/bin/activate"
    # List installed packages if monorepo
    if [ -d "packages" ]; then
        for pkg_dir in packages/*/; do
            if [ -f "${pkg_dir}pyproject.toml" ]; then
                pkg_name="${pkg_dir%/}"
                echo "    - $pkg_name (editable install)"
            fi
        done
    fi
fi

# Check for Node.js
if [ -f "./package.json" ]; then
    echo "  Node (root): npm run dev (or check package.json scripts)"
fi

# Check subdirectories for Node projects
for dirpath in */; do
    dirname=${dirpath%/}
    if [ -d "$dirname" ] && [ -f "$dirname/package.json" ]; then
        echo "  Node ($dirname): cd $dirname && npm run dev (or check package.json scripts)"
    fi
done 2>/dev/null || true