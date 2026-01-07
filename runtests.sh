#!/bin/bash

# Exit on any error
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Add common pip install locations to PATH
export PATH="$HOME/.local/bin:$PATH"

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "packages" ]]; then
    print_error "Run this script from the root of the devs repository"
    exit 1
fi

# Check for required Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed."
    exit 1
fi

# Install packages in development mode
print_status "Installing packages in development mode..."

# Determine pip install options for environment compatibility
PIP_OPTS=""
if pip install --help 2>&1 | grep -q -- '--break-system-packages'; then
    # Check if we're in an externally managed environment
    if python3 -c "import sysconfig; exit(0 if sysconfig.get_path('purelib').startswith('/usr') else 1)" 2>/dev/null; then
        PIP_OPTS="--break-system-packages"
    fi
fi

# Install common package (dependency for CLI and webhook)
print_status "Installing common package..."
pip install -e "packages/common[dev]" $PIP_OPTS --quiet

# Install CLI package
print_status "Installing CLI package..."
pip install -e "packages/cli[dev]" $PIP_OPTS --quiet

# Install webhook package
print_status "Installing webhook package..."
pip install -e "packages/webhook[dev]" $PIP_OPTS --quiet

# Check for pytest - try python -m pytest as fallback
PYTEST_CMD="pytest"
if ! command -v pytest &> /dev/null; then
    if python3 -m pytest --version &> /dev/null; then
        PYTEST_CMD="python3 -m pytest"
    else
        print_error "pytest is required but not installed."
        exit 1
    fi
fi

print_status "Running tests for all packages..."

# Track overall success
overall_success=true

# Test common package
print_status "Testing common package..."
if [ -d "packages/common/tests" ] && [ -n "$(ls packages/common/tests/*.py 2>/dev/null)" ]; then
    if $PYTEST_CMD packages/common/tests/ -v --tb=short; then
        print_status "Common package tests passed"
    else
        print_error "Common package tests failed"
        overall_success=false
    fi
else
    print_warning "No tests found for common package"
fi

# Test CLI package
print_status "Testing CLI package..."
if $PYTEST_CMD packages/cli/tests/ -v --tb=short; then
    print_status "CLI package tests passed"
else
    print_error "CLI package tests failed"
    overall_success=false
fi

# Test webhook package
print_status "Testing webhook package..."
if $PYTEST_CMD packages/webhook/tests/ -v --tb=short; then
    print_status "Webhook package tests passed"
else
    print_error "Webhook package tests failed"
    overall_success=false
fi

echo ""
if [ "$overall_success" = true ]; then
    print_status "All tests passed!"
    exit 0
else
    print_error "Some tests failed!"
    exit 1
fi
