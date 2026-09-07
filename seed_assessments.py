
import os
import random
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def seed_assessments():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    # 1. Get all patients
    pat_resp = supabase.table("patients").select("id").execute()
    patients = pat_resp.data

    # 2. Get a nurse/admin user ID for 'assessed_by'
    user_resp = supabase.table("users").select("id").limit(1).execute()
    user_id = user_resp.data[0]['id'] if user_resp.data else 1

    if not patients:
        print("No patients found. Please add patients first.")
        return

    print(f"Creating mock assessments for {len(patients)} patients...")

    for p in patients:
        # A. Create Encounter
        enc_data = {
            "patient_id": p['id'],
            "encounter_date": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
            "encounter_type": "cga",
            "created_by": user_id
        }
        enc_res = supabase.table("encounters").insert(enc_data).execute()
        enc_id = enc_res.data[0]['id']

        # B. Create Assessment Session
        sess_data = {
            "patient_id": p['id'],
            "encounter_id": enc_id,
            "status": "completed",
            "started_at": datetime.now().isoformat()
        }
        sess_res = supabase.table("assessment_sessions").insert(sess_data).execute()
        sess_id = sess_res.data[0]['id']

        # C. Create CGA Header
        risks = ['low', 'medium', 'high']
        cga_data = {
            "encounter_id": enc_id,
            "session_id": sess_id,
            "assessed_by": user_id,
            "assessed_at": datetime.now().isoformat(),
            "overall_risk": random.choice(risks),
            "note": "Generated mock assessment data"
        }
        cga_res = supabase.table("cga_headers").insert(cga_data).execute()
        cga_id = cga_res.data[0]['id']

        # D. Create individual scores (MMSE, TGDS)
        scores = [
            {"cga_id": cga_id, "session_id": sess_id, "instrument": "mmse", "total_score": random.randint(15, 30), "risk_level": "normal"},
            {"cga_id": cga_id, "session_id": sess_id, "instrument": "tgds", "total_score": random.randint(0, 15), "risk_level": "low"}
        ]
        supabase.table("assessment_scores").insert(scores).execute()

    print("Successfully generated mock assessment data.")

if __name__ == "__main__":
    seed_assessments()
