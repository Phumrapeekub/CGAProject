#!/bin/bash
set -e

# If MariaDB exists, start it optionally in background
if command -v mariadbd >/dev/null 2>&1 && [ -d "/app/mariadb/data" ]; then
    echo "=== Starting MariaDB Daemon (Local Fallback) ==="
    mkdir -p /app/mariadb/data /tmp/mysqld
    chmod 777 /tmp/mysqld 2>/dev/null || true
    mariadbd --datadir=/app/mariadb/data \
             --socket=/tmp/mysql.sock \
             --pid-file=/tmp/mysqld.pid \
             --port=3306 \
             --bind-address=0.0.0.0 &
    for i in {1..10}; do
        if mysqladmin ping --silent --socket=/tmp/mysql.sock 2>/dev/null; then
            echo "MariaDB is online!"
            break
        fi
        sleep 1
    done
fi

echo "=== Starting Gunicorn Server on Port 7860 (Pure Supabase Mode) ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2
