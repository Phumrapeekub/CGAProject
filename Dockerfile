# ใช้อิมเมจ Python 3.10 ขึ้นไปเป็นฐาน
FROM python:3.10-slim

# ติดตั้ง MariaDB Server, Client และ dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    mariadb-server \
    mariadb-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# กำหนด user UID 1000 สำหรับ Hugging Face Spaces
RUN useradd -m -u 1000 user

# สร้างไดเรกทอรีสำหรับ MySQL และกำหนดสิทธิ์ให้ user 1000
RUN mkdir -p /var/run/mysqld /var/lib/mysql /var/log/mysql /app \
    && chown -R 1000:1000 /var/run/mysqld /var/lib/mysql /var/log/mysql /app \
    && chmod -R 777 /var/run/mysqld /var/lib/mysql /var/log/mysql /app

WORKDIR /app

# คัดลอกไฟล์ requirements.txt และติดตั้งไลบรารี
COPY --chown=1000:1000 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดในโฟลเดอร์ปัจจุบันเข้าไปใน Container
COPY --chown=1000:1000 . .

# ตั้งค่าสิทธิ์และ line-ending ของ entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# เริ่มต้นฐานข้อมูล MariaDB และ Import init_db.sql ระหว่าง Docker Build
RUN mariadb-install-db --user=user --datadir=/var/lib/mysql --auth-root-authentication-method=normal && \
    mariadbd --user=user --datadir=/var/lib/mysql --socket=/var/run/mysqld/mysqld.sock --bind-address=127.0.0.1 & \
    MARIADB_PID=$! && \
    for i in $(seq 1 30); do \
        if mysqladmin ping --silent --socket=/var/run/mysqld/mysqld.sock 2>/dev/null; then break; fi; \
        sleep 1; \
    done && \
    mysql --socket=/var/run/mysqld/mysqld.sock -u root -e "CREATE DATABASE IF NOT EXISTS cga_system_dev;" && \
    mysql --socket=/var/run/mysqld/mysqld.sock -u root -e "CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'Kantiya203_'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION; CREATE USER IF NOT EXISTS 'root'@'localhost' IDENTIFIED BY 'Kantiya203_'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' WITH GRANT OPTION; FLUSH PRIVILEGES;" && \
    mysql --socket=/var/run/mysqld/mysqld.sock -u root cga_system_dev < /app/init_db.sql && \
    kill $MARIADB_PID && \
    wait $MARIADB_PID || true

USER 1000

# เปิด Port 7860 (ข้อบังคับของ Hugging Face Spaces)
EXPOSE 7860
ENV PORT=7860

# รัน entrypoint เพื่อเปิด MariaDB แล้วรัน Gunicorn
CMD ["/app/entrypoint.sh"]