# ใช้อิมเมจ Python 3.10 ขึ้นไปเป็นฐาน
FROM python:3.10-slim

# ติดตั้ง System dependencies ที่จำเป็น
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# แปลงสิทธิ์และ line-ending ของ entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

USER 1000

# เปิด Port 7860 (ข้อบังคับของ Hugging Face Spaces)
EXPOSE 7860
ENV PORT=7860

# รัน entrypoint เพื่อเริ่ม Gunicorn Server
CMD ["/app/entrypoint.sh"]