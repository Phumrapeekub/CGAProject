#!/bin/bash

# Start MariaDB in background using non-root user UID 1000
if command -v mariadbd >/dev/null 2>&1 && [ -d "/app/mariadb/data" ]; then
    echo "=== Starting MariaDB Daemon (Local DB Engine) ==="
    mkdir -p /app/mariadb/data /tmp/mysqld
    chmod 777 /tmp/mysqld /app/mariadb/data /tmp 2>/dev/null || true
    mariadbd --user=user \
             --datadir=/app/mariadb/data \
             --socket=/tmp/mysql.sock \
             --pid-file=/tmp/mysqld.pid \
             --port=3306 \
             --bind-address=0.0.0.0 &
    for i in $(seq 1 15); do
        if mysqladmin ping --silent --socket=/tmp/mysql.sock 2>/dev/null || mysqladmin ping --silent -h 127.0.0.1 -P 3306 2>/dev/null; then
            echo "MariaDB is online and ready!"
            break
        fi
        sleep 1
    done
fi

echo "=== Starting Gunicorn Server on Port 7860 ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2

