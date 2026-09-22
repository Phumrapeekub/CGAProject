# CGAProject/scripts/notify_appointments.py
import os
from datetime import datetime, timedelta
from linebot import LineBotApi
from linebot.models import TextSendMessage
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add project root to path to import db.db
sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_db_client

load_dotenv()

# Line Configuration (Add these to your .env)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None

def send_line_notification(line_id, message):
    if not line_bot_api:
        print("❌ LINE_CHANNEL_ACCESS_TOKEN not set")
        return False
    try:
        line_bot_api.push_message(line_id, TextSendMessage(text=message))
        return True
    except Exception as e:
        print(f"❌ Error sending Line message: {e}")
        return False

def notify_upcoming_appointments():
    """
    แจ้งเตือนนัดหมายที่จะถึงในวันพรุ่งนี้
    """
    supabase = get_db_client()
    if not supabase:
        print("❌ Supabase Client Error")
        return

    # หานัดหมายในวันพรุ่งนี้ (1 วันล่วงหน้า)
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    tomorrow_str = tomorrow.isoformat()
    
    try:
        # ดึงนัดหมายพรุ่งนี้พร้อมข้อมูลคนไข้และแพทย์
        # หมายเหตุ: Supabase SDK อาจจะกรองวันที่ใน query ได้ลำบากถ้าเป็น timestamptz
        # เราจะกรองด้วย status และ check patient has line_user_id ก่อน
        res = supabase.table("appointments").select(
            "id, appt_datetime, appt_type, patients!inner(full_name, line_user_id), users(full_name)"
        ).eq("status", "scheduled").not_.is_("patients.line_user_id", "null").execute()
        
        appointments = []
        for a in (res.data or []):
            # parse date and compare
            dt_val = a['appt_datetime']
            if not dt_val: continue
            
            appt_date = datetime.fromisoformat(dt_val.replace('Z', '+00:00')).date()
            if appt_date == tomorrow:
                appointments.append(a)
        
        print(f"Found {len(appointments)} appointments for {tomorrow}")
        
        for appt in appointments:
            p = appt.get('patients')
            u = appt.get('users')
            
            dt_obj = datetime.fromisoformat(appt['appt_datetime'].replace('Z', '+00:00'))
            appt_time = dt_obj.strftime("%H:%M")
            
            message = (
                f"🔔 แจ้งเตือนนัดหมายล่วงหน้า\n"
                f"คุณ {p['full_name']}\n"
                f"มีนัดตรวจ: {appt['appt_type']}\n"
                f"วันที่: {tomorrow.strftime('%d/%m/%Y')}\n"
                f"เวลา: {appt_time} น.\n"
                f"พบ: {u['full_name'] if u else 'แพทย์'}\n"
                f"กรุณามาถึงก่อนเวลานัด 15 นาทีค่ะ"
            )
            
            success = send_line_notification(p['line_user_id'], message)
            if success:
                print(f"✅ Notified {p['full_name']} (ID: {p['line_user_id']})")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print(f"🚀 Starting Appointment Notification Service at {datetime.now()}")
    notify_upcoming_appointments()
    print("🏁 Finished service")