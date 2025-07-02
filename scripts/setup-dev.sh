#!/bin/bash

# Development setup script for devs monorepo
set -euo pipefail

echo "🚀 Setting up devs monorepo for development..."

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "packages" ]]; then
    echo "❌ Error: Run this script from the root of the devs repository"
    exit 1
fi

# Check Python version
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Error: Python 3 is required but not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
echo "🐍 Using Python $PYTHON_VERSION"

# Install CLI package in development mode
echo ""
echo "📦 Installing CLI package in development mode..."
cd packages/cli
pip install -e ".[dev]"
cd ../..

echo ""
echo "✅ Development setup complete!"
echo ""
echo "Next steps:"
echo "  • Install global wrapper: ./scripts/install-dev-wrapper.sh"
echo "  • Run tests: cd packages/cli && pytest"
echo "  • Format code: cd packages/cli && black devs tests"
echo "  • Type check: cd packages/cli && mypy devs"
echo "  • Use CLI: devs --help (or devs-dev after wrapper install)"
echo ""
echo "Happy coding! 🎉"