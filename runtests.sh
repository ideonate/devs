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

# Test results directory - use TEST_RESULTS_FOLDER env var if set, otherwise default to test-results
TEST_RESULTS_BASE="${TEST_RESULTS_FOLDER:-test-results}"

# Create test results directories
print_status "Creating test results directories..."
mkdir -p "${TEST_RESULTS_BASE}"

# Check for required Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed."
    exit 1
fi

print_status "Using Python: $(python3 --version)"

# Create and activate virtual environment to avoid PEP 668 externally-managed-environment errors
VENV_DIR="${TEST_RESULTS_BASE}/.venv"
print_status "Creating virtual environment at ${VENV_DIR}..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
print_status "Virtual environment activated"

# Upgrade pip in the virtual environment
print_status "Upgrading pip..."
pip install --upgrade pip --quiet

# Install packages in development mode
print_status "Installing packages in development mode..."

print_status "Installing common package..."
pip install -e packages/common --quiet
if [ $? -ne 0 ]; then
    print_error "Failed to install common package"
    exit 1
fi

print_status "Installing cli package..."
pip install -e packages/cli --quiet
if [ $? -ne 0 ]; then
    print_error "Failed to install cli package"
    exit 1
fi

print_status "Installing webhook package..."
pip install -e packages/webhook --quiet
if [ $? -ne 0 ]; then
    print_error "Failed to install webhook package"
    exit 1
fi

# Install pytest and related dependencies
print_status "Installing pytest and dependencies..."
pip install pytest pytest-html pytest-json-report pytest-md-report --quiet

# Track overall test status
OVERALL_EXIT_CODE=0

# Run simpler CLI package tests (tests that don't require Docker)
# These include project tests which use mocks for git operations
print_status "Running CLI package tests (simpler tests only)..."
CLI_RESULTS_DIR="${TEST_RESULTS_BASE}/cli"
mkdir -p "${CLI_RESULTS_DIR}"

pytest packages/cli/tests/test_project.py -v --tb=short \
    --html="${CLI_RESULTS_DIR}/report.html" --self-contained-html \
    --json-report --json-report-file="${CLI_RESULTS_DIR}/report.json" --json-report-indent=2 \
    --md-report --md-report-flavor gfm --md-report-output "${CLI_RESULTS_DIR}/report.md" \
    || OVERALL_EXIT_CODE=1

if [ $OVERALL_EXIT_CODE -eq 0 ]; then
    print_status "CLI package tests passed!"
else
    print_error "CLI package tests failed!"
fi

# Run Webhook package tests (all are simpler tests, no Docker required)
print_status "Running Webhook package tests..."
WEBHOOK_RESULTS_DIR="${TEST_RESULTS_BASE}/webhook"
mkdir -p "${WEBHOOK_RESULTS_DIR}"

pytest packages/webhook/tests/ -v --tb=short \
    --html="${WEBHOOK_RESULTS_DIR}/report.html" --self-contained-html \
    --json-report --json-report-file="${WEBHOOK_RESULTS_DIR}/report.json" --json-report-indent=2 \
    --md-report --md-report-flavor gfm --md-report-output "${WEBHOOK_RESULTS_DIR}/report.md" \
    || OVERALL_EXIT_CODE=1

if [ $OVERALL_EXIT_CODE -eq 0 ]; then
    print_status "Webhook package tests passed!"
else
    print_error "Some tests failed!"
fi

# Summary
echo ""
print_status "Test results written to: ${TEST_RESULTS_BASE}/"
print_status "  - CLI results: ${CLI_RESULTS_DIR}/"
print_status "  - Webhook results: ${WEBHOOK_RESULTS_DIR}/"

if [ $OVERALL_EXIT_CODE -eq 0 ]; then
    print_status "All tests completed successfully!"
else
    print_error "Some tests failed. Check the reports for details."
fi

exit $OVERALL_EXIT_CODE