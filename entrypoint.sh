#!/bin/bash
set -e

echo "=== Starting MariaDB Database Daemon ==="
mkdir -p /var/run/mysqld /var/lib/mysql /var/log/mysql
mariadbd --user=user --datadir=/var/lib/mysql --socket=/var/run/mysqld/mysqld.sock --port=3306 --bind-address=127.0.0.1 &

# Wait up to 15 seconds for MariaDB to respond
echo "Waiting for MariaDB to be available on port 3306..."
for i in {1..15}; do
    if mysqladmin ping --silent -h 127.0.0.1 -P 3306 2>/dev/null; then
        echo "MariaDB is online and ready!"
        break
    fi
    sleep 1
done

echo "=== Starting Gunicorn Server on Port 7860 ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2
