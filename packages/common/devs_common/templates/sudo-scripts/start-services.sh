#!/bin/bash
set -euo pipefail

echo "Starting database services..."

# Start MariaDB (MySQL) if not running
if ! pgrep -x mysqld > /dev/null; then
    echo "Starting MariaDB (MySQL)..."
    service mariadb start
    
    # Wait for MariaDB to be ready
    for i in {1..30}; do
        if mysqladmin ping &>/dev/null; then
            echo "✅ MariaDB (MySQL) is running"
            break
        fi
        sleep 1
    done
    
    # Initialize MariaDB without password for development
    mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '';" 2>/dev/null || true
    mysql -e "FLUSH PRIVILEGES;" 2>/dev/null || true
else
    echo "✅ MariaDB (MySQL) is already running"
fi

# Start Redis if not running
if ! pgrep -x redis-server > /dev/null; then
    echo "Starting Redis..."
    service redis-server start
    
    # Wait for Redis to be ready
    for i in {1..10}; do
        if redis-cli ping &>/dev/null; then
            echo "✅ Redis is running"
            break
        fi
        sleep 1
    done
else
    echo "✅ Redis is already running"
fi

echo "All services started successfully!"