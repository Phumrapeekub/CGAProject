#!/bin/bash
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# Start MariaDB in background using non-root user UID 1000
echo "=== Checking MariaDB Daemon ==="
mkdir -p /app/mariadb/data /tmp/mysqld
chmod 777 /tmp/mysqld /app/mariadb/data /tmp 2>/dev/null || true

MARIADB_EXEC=""
if [ -f "/usr/sbin/mariadbd" ]; then
    MARIADB_EXEC="/usr/sbin/mariadbd"
elif command -v mariadbd >/dev/null 2>&1; then
    MARIADB_EXEC=$(command -v mariadbd)
fi

if [ -n "$MARIADB_EXEC" ] && [ -d "/app/mariadb/data" ]; then
    echo "=== Starting MariaDB Daemon: $MARIADB_EXEC ==="
    $MARIADB_EXEC --user=user \
                  --datadir=/app/mariadb/data \
                  --socket=/tmp/mysql.sock \
                  --pid-file=/tmp/mysqld.pid \
                  --port=3306 \
                  --bind-address=0.0.0.0 &
    for i in $(seq 1 20); do
        if mysqladmin ping --silent --socket=/tmp/mysql.sock 2>/dev/null || mysqladmin ping --silent -h 127.0.0.1 -P 3306 2>/dev/null; then
            echo "MariaDB is online and ready!"
            mysql --socket=/tmp/mysql.sock -u root -e "CREATE DATABASE IF NOT EXISTS cga_system_dev;" 2>/dev/null || true
            if [ -f "/app/init_db.sql" ]; then
                mysql --socket=/tmp/mysql.sock -u root cga_system_dev < /app/init_db.sql 2>/dev/null || true
            fi
            break
        fi
        sleep 1
    done
fi

echo "=== Starting Gunicorn Server on Port 7860 ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2


