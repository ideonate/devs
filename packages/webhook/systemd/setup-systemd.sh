#!/bin/bash
# Setup script for devs-webhook systemd service

set -e

# Default values
SERVICE_NAME="devs-webhook"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TEMPLATE_FILE="$(dirname "$0")/${SERVICE_NAME}.service"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[!]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[*]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root. Run as your regular user and it will use sudo when needed."
   exit 1
fi

# Parse command line arguments
INSTALL_USER="${USER}"
INSTALL_GROUP="${USER}"
WORKING_DIR="${PWD}"
ENV_FILE=""
PYTHON_PATH=$(which python3)

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)
            INSTALL_USER="$2"
            shift 2
            ;;
        --group)
            INSTALL_GROUP="$2"
            shift 2
            ;;
        --working-dir)
            WORKING_DIR="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --python-path)
            PYTHON_PATH="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --user USER           User to run the service as (default: current user)"
            echo "  --group GROUP         Group to run the service as (default: current user)"
            echo "  --working-dir DIR     Working directory for the service (default: current directory)"
            echo "  --env-file FILE       Path to .env file (required)"
            echo "  --python-path PATH    Path to Python executable (default: $(which python3))"
            echo "  --help                Show this help message"
            echo ""
            echo "Example:"
            echo "  $0 --user dan --working-dir /home/dan/Dev/devs --env-file /home/dan/Dev/devs/.env"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$ENV_FILE" ]]; then
    print_error "Error: --env-file is required"
    echo "Run '$0 --help' for usage information"
    exit 1
fi

# Validate paths
if [[ ! -f "$ENV_FILE" ]]; then
    print_error "Error: Environment file not found: $ENV_FILE"
    exit 1
fi

if [[ ! -d "$WORKING_DIR" ]]; then
    print_error "Error: Working directory not found: $WORKING_DIR"
    exit 1
fi

if [[ ! -f "$TEMPLATE_FILE" ]]; then
    print_error "Error: Service template not found: $TEMPLATE_FILE"
    exit 1
fi

# Convert to absolute paths
ENV_FILE=$(realpath "$ENV_FILE")
WORKING_DIR=$(realpath "$WORKING_DIR")

print_status "Setting up devs-webhook systemd service..."
echo ""
echo "Configuration:"
echo "  User: $INSTALL_USER"
echo "  Group: $INSTALL_GROUP"
echo "  Working Directory: $WORKING_DIR"
echo "  Environment File: $ENV_FILE"
echo "  Python Path: $PYTHON_PATH"
echo ""

# Check if service already exists
if [[ -f "$SERVICE_FILE" ]]; then
    print_warning "Service file already exists: $SERVICE_FILE"
    read -p "Do you want to overwrite it? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Installation cancelled"
        exit 1
    fi
    
    # Stop existing service if running
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        print_status "Stopping existing service..."
        sudo systemctl stop "$SERVICE_NAME"
    fi
fi

# Create service file from template
print_status "Creating service file..."
sudo sed -e "s|%USER%|$INSTALL_USER|g" \
         -e "s|%GROUP%|$INSTALL_GROUP|g" \
         -e "s|%WORKING_DIR%|$WORKING_DIR|g" \
         -e "s|%ENV_FILE%|$ENV_FILE|g" \
         -e "s|%PYTHON_PATH%|$PYTHON_PATH|g" \
         "$TEMPLATE_FILE" | sudo tee "$SERVICE_FILE" > /dev/null

# Reload systemd
print_status "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable service
print_status "Enabling service..."
sudo systemctl enable "$SERVICE_NAME"

# Display status
print_status "Service setup complete!"
echo ""
echo "To manage the service, use:"
echo "  sudo systemctl start $SERVICE_NAME    # Start the service"
echo "  sudo systemctl stop $SERVICE_NAME     # Stop the service"
echo "  sudo systemctl restart $SERVICE_NAME  # Restart the service"
echo "  sudo systemctl status $SERVICE_NAME   # Check service status"
echo "  sudo journalctl -u $SERVICE_NAME -f  # Follow service logs"
echo ""

# Ask if user wants to start the service now
read -p "Do you want to start the service now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Starting service..."
    sudo systemctl start "$SERVICE_NAME"
    
    # Wait a moment for service to start
    sleep 2
    
    # Check status
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        print_status "Service started successfully!"
        echo ""
        sudo systemctl status "$SERVICE_NAME" --no-pager
    else
        print_error "Service failed to start"
        echo ""
        sudo journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    fi
fi