# ใช้อิมเมจ Python 3.10 ขึ้นไปเป็นฐาน
FROM python:3.10-slim

# ติดตั้ง MariaDB Server, Client และ dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    mariadb-server \
    mariadb-client \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# กำหนด user UID 1000 สำหรับ Hugging Face Spaces
RUN useradd -m -u 1000 user

WORKDIR /app

# คัดลอกไฟล์ requirements.txt และติดตั้งไลบรารี
COPY --chown=1000:1000 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดในโฟลเดอร์ปัจจุบันเข้าไปใน Container
COPY --chown=1000:1000 . .

# สร้างไดเรกทอรีสำหรับ MariaDB ภายใน /app และ /tmp
RUN mkdir -p /app/mariadb/data /tmp/mysqld && \
    chown -R 1000:1000 /app && \
    chmod -R 777 /app/mariadb /tmp

# เริ่มต้นฐานข้อมูล MariaDB และ Import init_db.sql ระหว่าง Docker Build
RUN mariadb-install-db --user=user --datadir=/app/mariadb/data --auth-root-authentication-method=normal && \
    mariadbd --user=user --datadir=/app/mariadb/data --socket=/tmp/mysql.sock --bind-address=0.0.0.0 & \
    MARIADB_PID=$! && \
    for i in $(seq 1 30); do \
        if mysqladmin ping --silent --socket=/tmp/mysql.sock 2>/dev/null; then break; fi; \
        sleep 1; \
    done && \
    mysql --socket=/tmp/mysql.sock -u root -e "CREATE DATABASE IF NOT EXISTS cga_system_dev;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY 'Kantiya203_' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' IDENTIFIED BY 'Kantiya203_' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' IDENTIFIED BY 'Kantiya203_' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;" && \
    mysql --socket=/tmp/mysql.sock -u root -e "FLUSH PRIVILEGES;" && \
    mysql --socket=/tmp/mysql.sock -u root cga_system_dev < /app/init_db.sql && \
    kill $MARIADB_PID && \
    wait $MARIADB_PID || true

# แปลงสิทธิ์และ line-ending ของ entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# กำหนดสิทธิ์ให้ user 1000 ใช้งานได้เต็มที่
RUN chown -R 1000:1000 /app && chmod -R 777 /app/mariadb

USER 1000

# เปิด Port 7860 (ข้อบังคับของ Hugging Face Spaces)
EXPOSE 7860
ENV PORT=7860
ENV DB_HOST=127.0.0.1
ENV DB_PORT=3306
ENV DB_USER=root
ENV DB_PASSWORD=Kantiya203_
ENV DB_NAME=cga_system_dev

# รัน entrypoint เพื่อเปิด MariaDB แล้วรัน Gunicorn
CMD ["/app/entrypoint.sh"]