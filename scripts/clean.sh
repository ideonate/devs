#!/bin/bash

# Clean build artifacts and cache files from all packages
set -euo pipefail

echo "🧹 Cleaning build artifacts and cache files..."

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "packages" ]]; then
    echo "❌ Error: Run this script from the root of the devs repository"
    exit 1
fi

# Function to clean a directory
clean_directory() {
    local dir="$1"
    local name="$2"
    
    if [[ -d "$dir" ]]; then
        echo "📦 Cleaning $name..."
        
        # Remove Python cache files
        find "$dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$dir" -name "*.pyc" -delete 2>/dev/null || true
        find "$dir" -name "*.pyo" -delete 2>/dev/null || true
        
        # Remove build directories
        rm -rf "$dir"/build
        rm -rf "$dir"/dist
        rm -rf "$dir"/*.egg-info
        
        # Remove test artifacts
        rm -rf "$dir"/.pytest_cache
        rm -rf "$dir"/.coverage
        rm -rf "$dir"/htmlcov
        
        # Remove mypy cache
        rm -rf "$dir"/.mypy_cache
        
        echo "  ✅ $name cleaned"
    fi
}

# Clean CLI package
clean_directory "packages/cli" "CLI package"

# Future: Clean other packages when they exist
# clean_directory "packages/webhook" "Webhook package"
# clean_directory "packages/common" "Common package"

# Clean root level cache files
echo "🗑️  Cleaning root level cache files..."
find . -name ".DS_Store" -delete 2>/dev/null || true

echo ""
echo "🎉 All clean!"