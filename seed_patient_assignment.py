
import os
import random
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def link_patients_to_doctors():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    # 1. ดึงรายชื่อแพทย์
    doc_resp = supabase.table("users").select("id").eq("role", "doctor").execute()
    doctors = [d['id'] for d in doc_resp.data]

    if not doctors:
        print("Error: No doctors found in database.")
        return

    # 2. ดึงรายชื่อผู้ป่วย
    pat_resp = supabase.table("patients").select("id").execute()
    patients = pat_resp.data

    if not patients:
        print("No patients found to assign.")
        return

    print(f"Assigning {len(patients)} patients to {len(doctors)} doctors...")

    for p in patients:
        # สุ่มเลือกแพทย์ 1 ท่านให้ผู้ป่วยแต่ละคน
        assigned_doctor_id = random.choice(doctors)
        try:
            supabase.table("patients").update({"primary_doctor_id": assigned_doctor_id}).eq("id", p['id']).execute()
        except Exception as e:
            print(f"Failed to update patient {p['id']}: {e}")

    print("Successfully assigned patients to doctors.")

if __name__ == "__main__":
    link_patients_to_doctors()
