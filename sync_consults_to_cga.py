import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def sync_consults_to_cga():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("✅ Connected to Supabase")

        # 1. Fetch all consultations
        print("Fetching consultations...")
        cons_resp = supabase.table("consultations").select("*").execute()
        consultations = cons_resp.data
        print(f"   - Found {len(consultations)} consultation records.")

        # 2. Fetch all existing cga_records to check for duplicates
        print("Fetching existing cga_records...")
        cga_resp = supabase.table("cga_records").select("hn, assessed_date").execute()
        # Create a set of (hn, date) for quick lookup
        existing_cga = set()
        for r in cga_resp.data:
            d = r.get('assessed_date')
            existing_cga.add((r['hn'], str(d)))

        # 3. Fetch patient mapping {hn: (id, full_name)}
        print("Fetching patient mapping...")
        pat_resp = supabase.table("patients").select("id, hn, full_name").execute()
        patient_map = {p['hn']: (p['id'], p['full_name']) for p in pat_resp.data}

        # 4. Sync missing records
        synced_count = 0
        
        for con in consultations:
            hn = con.get('hn')
            # Determine date: use created_at date part
            raw_date = con.get('created_at', '')
            date_str = raw_date[:10] if raw_date else str(datetime.now().date())
            
            if not hn: continue

            # If this consultation (HN + Date) is NOT in cga_records, we need to add it
            if (hn, date_str) not in existing_cga:
                if hn in patient_map:
                    p_id, p_name = patient_map[hn]
                    
                    # Prepare data for cga_records
                    new_record = {
                        "patient_id": p_id,
                        "encounter_id": con.get('id'), # Use consultation ID as encounter link
                        "hn": hn,
                        "full_name": p_name,
                        "assessed_date": date_str,
                        "mmse_result": con.get('diagnosis') or con.get('result') or "Consultation Data",
                        "mmse_score": 0, # Placeholder
                        "tgds_score": 0, # Placeholder
                        "created_at": con.get('created_at')
                    }
                    
                    try:
                        supabase.table("cga_records").insert(new_record).execute()
                        synced_count += 1
                        print(f"   ✅ Synced: {hn} on {date_str}")
                        # Add to set to prevent duplicate inserts in the same run
                        existing_cga.add((hn, date_str))
                    except Exception as e:
                        print(f"   ⚠️ Could not sync {hn}: {e}")
                else:
                    print(f"   ❓ Patient with HN {hn} not found in master patients table.")

        print(f"\n✨ Sync Complete! Added {synced_count} records to cga_records.")

    except Exception as e:
        print(f"❌ Supabase Error: {e}")

if __name__ == "__main__":
    sync_consults_to_cga()
