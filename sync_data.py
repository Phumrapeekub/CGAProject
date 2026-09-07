
import os
import random
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def sync_patients_and_appointments():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    # 1. ดึงรายชื่อแพทย์ทั้งหมด
    doc_resp = supabase.table("users").select("id").eq("role", "doctor").execute()
    doctor_ids = [d['id'] for d in doc_resp.data]

    if not doctor_ids:
        print("Error: No doctors found.")
        return

    # 2. ดึงรายชื่อคนไข้ทุกคน
    pat_resp = supabase.table("patients").select("id, full_name, primary_doctor_id").execute()
    patients = pat_resp.data

    # 3. ลบการนัดหมายเก่าทิ้งก่อน (Optional - เพื่อความสะอาดของข้อมูล)
    # หมายเหตุ: ในระบบจริงไม่ควรลบ แต่อันนี้เป็นการทำข้อมูล Demo
    supabase.table("appointments").delete().neq("id", 0).execute()

    print(f"Processing {len(patients)} patients...")

    new_appointments = []

    for p in patients:
        # ถ้าคนไข้ยังไม่มีแพทย์เจ้าของไข้ ให้สุ่มใส่ให้
        doc_id = p.get('primary_doctor_id')
        if not doc_id:
            doc_id = random.choice(doctor_ids)
            supabase.table("patients").update({"primary_doctor_id": doc_id}).eq("id", p['id']).execute()
        
        # สร้างการนัดหมายให้คนไข้ 1 รายการ โดยใช้หมอคนเดียวกัน
        days_offset = random.randint(1, 20) # นัดล่วงหน้า 1-20 วัน
        appt_time = datetime.now() + timedelta(days=days_offset)
        appt_time = appt_time.replace(hour=random.randint(9, 15), minute=0, second=0, microsecond=0)

        appt = {
            "patient_id": p['id'],
            "created_by_doctor": doc_id, # ใช้ ID หมอเจ้าของไข้
            "appt_datetime": appt_time.isoformat(),
            "appt_type": "followup",
            "status": "scheduled",
            "note": f"นัดตรวจติดตามอาการโดยแพทย์เจ้าของไข้"
        }
        new_appointments.append(appt)

    # 4. บันทึกข้อมูลการนัดหมายลงตาราง
    if new_appointments:
        supabase.table("appointments").insert(new_appointments).execute()
        print(f"Successfully synced {len(new_appointments)} patients with their primary doctors and appointments.")

if __name__ == "__main__":
    sync_patients_and_appointments()
