#!/bin/bash
echo "=== Starting MariaDB Database Daemon ==="
mkdir -p /app/mariadb/data /tmp/mysqld
chmod 777 /tmp/mysqld 2>/dev/null || true

# Start mariadbd in background using /app/mariadb/data
mariadbd --datadir=/app/mariadb/data \
         --socket=/tmp/mysql.sock \
         --pid-file=/tmp/mysqld.pid \
         --port=3306 \
         --bind-address=0.0.0.0 &
MARIADB_PID=$!

echo "Waiting for MariaDB to be available on socket or port 3306..."
for i in {1..20}; do
    if mysqladmin ping --silent --socket=/tmp/mysql.sock 2>/dev/null || mysqladmin ping --silent -h 127.0.0.1 -P 3306 2>/dev/null; then
        echo "MariaDB is online and ready!"
        break
    fi
    sleep 1
done

echo "=== Starting Gunicorn Server on Port 7860 ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2
