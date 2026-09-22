from __future__ import annotations
import os
import atexit
from datetime import datetime, timedelta
from flask import Flask, request, abort, redirect
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp
from db.db import get_db_client
from scripts.notify_appointments import notify_upcoming_appointments
from Line.routes_line import line_bp


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

# --- LINE CONFIG (v3) ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- WEBHOOK ROUTE ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(400)
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
        
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    
    # ตรวจสอบคำสั่ง "ลงทะเบียน HNxxxx"
    if text.startswith("ลงทะเบียน"):
        parts = text.split()
        if len(parts) >= 2:
            hn_input = parts[1].strip()
            
            supabase = get_db_client()
            try:
                # เช็คก่อนว่ามี HN นี้ไหม
                res = supabase.table("patients").select("id, full_name").eq("hn", hn_input).execute()
                if res.data:
                    patient = res.data[0]
                    # อัปเดต Line ID
                    supabase.table("patients").update({"line_user_id": user_id}).eq("id", patient['id']).execute()
                    
                    reply_txt = f"✅ เชื่อมต่อสำเร็จ!\nคุณ {patient['full_name']} (HN: {hn_input})\nระบบจะแจ้งเตือนนัดหมายผ่านไลน์นี้ครับ"
                else:
                    reply_txt = f"❌ ไม่พบ HN: {hn_input} ในระบบ\nกรุณาตรวจสอบความถูกต้อง"
            except Exception as e:
                print(f"Update Error: {e}")
                reply_txt = "❌ เกิดข้อผิดพลาดในการเชื่อมต่อระบบ"
        else:
            reply_txt = "⚠️ รูปแบบไม่ถูกต้อง\nพิมพ์: ลงทะเบียน [เลขHN]\nเช่น: ลงทะเบียน HN001"
            
        # ส่งข้อความตอบกลับ (v3)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_txt)]
                )
            )

# --------------------------------------------------

# --- ตั้งเวลาแจ้งเตือนอัตโนมัติ ---
scheduler = BackgroundScheduler()

# 1. แจ้งเตือนทุกวัน 08:00 น.
scheduler.add_job(func=notify_upcoming_appointments, trigger="cron", hour=8, minute=0)

# 2. แจ้งเตือนทันทีที่รันโปรแกรม (เพื่อให้ทำงานเลยตอนนี้)
scheduler.add_job(func=notify_upcoming_appointments, trigger="date", run_date=datetime.now() + timedelta(seconds=5))

scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# --------------------------------------------------

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(nurse_bp)
app.register_blueprint(line_bp)

@app.get("/")
def root():
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True, port=5000)