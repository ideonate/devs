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
    
    # Create a development user 'dbuser' with password 'dbuser' and full privileges
    # Using sudo mysql since initial connection requires socket auth (as root)
    echo "Creating dbuser..."
    sudo mysql -e "CREATE USER IF NOT EXISTS 'dbuser'@'localhost' IDENTIFIED BY 'dbuser';" || echo "Failed to create dbuser@localhost"
    sudo mysql -e "CREATE USER IF NOT EXISTS 'dbuser'@'127.0.0.1' IDENTIFIED BY 'dbuser';" || echo "Failed to create dbuser@127.0.0.1"
    sudo mysql -e "CREATE USER IF NOT EXISTS 'dbuser'@'%' IDENTIFIED BY 'dbuser';" || echo "Failed to create dbuser@%"
    sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'dbuser'@'localhost' WITH GRANT OPTION;" || echo "Failed to grant privileges to dbuser@localhost"
    sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'dbuser'@'127.0.0.1' WITH GRANT OPTION;" || echo "Failed to grant privileges to dbuser@127.0.0.1"
    sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'dbuser'@'%' WITH GRANT OPTION;" || echo "Failed to grant privileges to dbuser@%"

    echo "Flushing privileges..."
    sudo mysql -e "FLUSH PRIVILEGES;" || echo "Failed to flush privileges"

    echo "✅ Database users configured: dbuser (password: dbuser)"
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