#!/bin/bash
# Simple wrapper for taking webapp screenshots during development

set -euo pipefail

echo "🖼️  Taking webapp screenshots..."

# Check if we're in a project directory
if [ ! -f "CLAUDE.md" ] && [ ! -f "package.json" ] && [ ! -f "requirements.txt" ]; then
    echo "⚠️  Not in a recognized project directory. Screenshots will still work but auto-server detection may not."
fi

# Use the playwright virtual environment if it exists, otherwise try to create one
if [ -d "playwright" ] && [ -f "playwright/requirements.txt" ]; then
    echo "📦 Setting up Playwright environment..."
    cd playwright
    
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment for Playwright..."
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    
    # Install Playwright browsers if not already installed
    playwright install chromium --with-deps 2>/dev/null || echo "Playwright browsers already installed"
    
    cd ..
    
    echo "🚀 Starting webapp screenshot capture (headless mode)..."
    # Use the activated environment to run our screenshot script
    python3 /usr/local/bin/webapp-screenshot.py --start-servers --headless "$@"
else
    echo "❌ No playwright directory found. Please set up Playwright first:"
    echo "   mkdir playwright"
    echo "   cd playwright"
    echo "   pip install playwright pytest"
    echo "   playwright install chromium"
    exit 1
fi

echo "✅ Screenshots complete! Check the webapp-screenshots/ directory."