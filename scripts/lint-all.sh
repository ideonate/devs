#!/bin/bash

# Lint and format all packages in the monorepo
set -euo pipefail

echo "🧹 Linting and formatting all packages..."

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "packages" ]]; then
    echo "❌ Error: Run this script from the root of the devs repository"
    exit 1
fi

# Track overall success
overall_success=true

# Lint CLI package
echo ""
echo "📦 Linting CLI package..."
cd packages/cli

echo "  🎨 Running black formatter..."
if black devs tests --check --diff; then
    echo "  ✅ Black formatting is good"
else
    echo "  ❌ Black formatting needs fixing. Run: black devs tests"
    overall_success=false
fi

echo "  🔍 Running flake8 linter..."
if flake8 devs tests; then
    echo "  ✅ Flake8 linting passed"
else
    echo "  ❌ Flake8 linting failed"
    overall_success=false
fi

echo "  🧐 Running mypy type checker..."
if mypy devs; then
    echo "  ✅ MyPy type checking passed"
else
    echo "  ❌ MyPy type checking failed"
    overall_success=false
fi

cd ../..

# Future: Lint other packages when they exist
# echo ""
# echo "📦 Linting webhook package..."
# cd packages/webhook
# black webhook tests --check --diff
# flake8 webhook tests
# mypy webhook
# cd ../..

echo ""
if [ "$overall_success" = true ]; then
    echo "🎉 All linting passed!"
    exit 0
else
    echo "💥 Some linting failed!"
    echo ""
    echo "To fix formatting issues, run:"
    echo "  cd packages/cli && black devs tests"
    exit 1
fi