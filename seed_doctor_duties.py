
import os
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def seed_doctor_duties():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env file")
        return

    supabase = create_client(url, key)

    # 1. Get all doctors
    response = supabase.table("users").select("id, full_name").eq("role", "doctor").execute()
    doctors = response.data

    if not doctors:
        print("No doctors found in the database.")
        return

    print(f"Found {len(doctors)} doctors. Adding sample duty events...")

    for doctor in doctors:
        doctor_id = doctor['id']
        doctor_name = doctor['full_name']
        
        # Create a duty for tomorrow
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=16, minute=0, second=0, microsecond=0)

        duty_data = {
            "doctor_id": doctor_id,
            "title": "เวรเช้า (ตรวจทั่วไป)",
            "note": f"เวรประจำวันสำหรับ {doctor_name}",
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat()
        }

        try:
            supabase.table("doctor_duty_events").insert(duty_data).execute()
            print(f"Added duty for {doctor_name} on {start_time.strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"Failed to add duty for {doctor_name}: {e}")

    print("Done!")

if __name__ == "__main__":
    seed_doctor_duties()
