# ใช้อิมเมจ Python 3.10 ขึ้นไปเป็นฐาน
FROM python:3.10-slim

# ตั้งค่า Directory ทำงานภายใน Container
WORKDIR /app

# คัดลอกไฟล์ requirements.txt และติดตั้งไลบรารี
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดในโฟลเดอร์ปัจจุบันเข้าไปใน Container
COPY . .

# เปิด Port 7860 (ข้อบังคับของ Hugging Face Spaces)
EXPOSE 7860

# ตั้งค่าตัวแปรสภาพแวดล้อมให้รับ Port ให้ถูกต้อง
ENV PORT=7860

# ใช้ gunicorn ในการรันแอป Flask ให้เสถียรระดับ Production
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app", "--timeout", "120", "--workers", "2"]