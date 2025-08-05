#!/bin/bash
# Uninstall script for devs-webhook systemd service

set -e

SERVICE_NAME="devs-webhook"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

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

# Check if service exists
if [[ ! -f "$SERVICE_FILE" ]]; then
    print_error "Service not found: $SERVICE_FILE"
    print_warning "Nothing to uninstall"
    exit 0
fi

print_status "Uninstalling devs-webhook systemd service..."

# Stop service if running
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    print_status "Stopping service..."
    sudo systemctl stop "$SERVICE_NAME"
fi

# Disable service
if sudo systemctl is-enabled --quiet "$SERVICE_NAME"; then
    print_status "Disabling service..."
    sudo systemctl disable "$SERVICE_NAME"
fi

# Remove service file
print_status "Removing service file..."
sudo rm "$SERVICE_FILE"

# Reload systemd
print_status "Reloading systemd daemon..."
sudo systemctl daemon-reload

print_status "Service uninstalled successfully!"