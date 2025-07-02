#!/bin/bash

# Run tests for all packages in the monorepo
set -euo pipefail

echo "🧪 Running tests for all packages..."

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "packages" ]]; then
    echo "❌ Error: Run this script from the root of the devs repository"
    exit 1
fi

# Track overall success
overall_success=true

# Test CLI package
echo ""
echo "📦 Testing CLI package..."
if cd packages/cli && pytest -v --tb=short; then
    echo "✅ CLI tests passed"
    cd ../..
else
    echo "❌ CLI tests failed"
    overall_success=false
    cd ../..
fi

# Future: Test other packages when they exist
# echo ""
# echo "📦 Testing webhook package..."
# if cd packages/webhook && pytest -v --tb=short; then
#     echo "✅ Webhook tests passed"
#     cd ../..
# else
#     echo "❌ Webhook tests failed"
#     overall_success=false
#     cd ../..
# fi

echo ""
if [ "$overall_success" = true ]; then
    echo "🎉 All tests passed!"
    exit 0
else
    echo "💥 Some tests failed!"
    exit 1
fi