#!/bin/bash

# Example test script for devs CI system
echo "🧪 Starting tests..."
echo "📂 Current directory: $(pwd)"
echo "📋 Available files:"
ls -la

echo ""
echo "🔍 Running example tests..."

# Example: Check if certain files exist
if [ -f "README.md" ]; then
    echo "✅ README.md found"
else
    echo "❌ README.md missing"
    exit 1
fi

# Example: Run a simple Python test
if command -v python &> /dev/null; then
    echo "🐍 Running Python version check..."
    python --version
    
    # Run a simple test
    echo "🧮 Running basic Python test..."
    python -c "
import sys
print(f'✅ Python test passed - version {sys.version}')
assert 2 + 2 == 4
print('✅ Math works correctly')
"
    if [ $? -eq 0 ]; then
        echo "✅ Python tests passed"
    else
        echo "❌ Python tests failed"
        exit 1
    fi
else
    echo "⚠️  Python not found, skipping Python tests"
fi

# Example: Check Node.js if available
if command -v node &> /dev/null; then
    echo "📦 Node.js found: $(node --version)"
    echo "✅ Node.js test passed"
else
    echo "📦 Node.js not found, skipping Node tests"
fi

echo ""
echo "🎉 All tests completed successfully!"
echo "📊 Test summary:"
echo "   - File existence checks: ✅"
echo "   - Python tests: ✅" 
echo "   - Node.js tests: $(command -v node &> /dev/null && echo "✅" || echo "⚠️ skipped")"

exit 0