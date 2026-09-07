
import os
import random
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def seed_appointments():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    # 1. Get all patients
    pat_resp = supabase.table("patients").select("id, full_name").execute()
    patients = pat_resp.data

    if not patients:
        print("No patients found. Please add patients first.")
        return

    # 2. Get all doctors
    doc_resp = supabase.table("users").select("id").eq("role", "doctor").execute()
    doctors = [d['id'] for d in doc_resp.data]

    if not doctors:
        print("No doctors found. Please add doctors first.")
        return

    print(f"Found {len(patients)} patients and {len(doctors)} doctors.")
    
    # 3. Optional: Clear existing appointments (uncomment if desired)
    # supabase.table("appointments").delete().neq("id", 0).execute()

    appt_types = ['followup', 'cga', 'other']
    statuses = ['scheduled', 'completed', 'cancelled', 'no_show']
    
    new_appointments = []

    for patient in patients:
        # Create 1-2 appointments per patient
        num_appts = random.randint(1, 2)
        
        for _ in range(num_appts):
            # Random date in the future or recent past
            days_offset = random.randint(-10, 30)
            appt_time = datetime.now() + timedelta(days=days_offset)
            appt_time = appt_time.replace(hour=random.randint(9, 16), minute=random.choice([0, 15, 30, 45]), second=0, microsecond=0)

            status = 'scheduled' if days_offset > 0 else random.choice(['completed', 'no_show'])
            
            appt = {
                "patient_id": patient['id'],
                "created_by_doctor": random.choice(doctors),
                "appt_datetime": appt_time.isoformat(),
                "appt_type": random.choice(appt_types),
                "status": status,
                "note": f"นัดตรวจติดตามอาการสำหรับคุณ {patient['full_name']}"
            }
            new_appointments.append(appt)

    if new_appointments:
        try:
            supabase.table("appointments").insert(new_appointments).execute()
            print(f"Successfully added {len(new_appointments)} appointments.")
        except Exception as e:
            print(f"Error inserting appointments: {e}")

if __name__ == "__main__":
    seed_appointments()
