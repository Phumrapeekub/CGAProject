import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def sync_links():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("✅ Connected to Supabase")

        # 1. Fetch all patients to build a mapping {hn: id}
        print("Fetching patients data...")
        patients_resp = supabase.table("patients").select("id, hn").execute()
        patient_map = {p['hn']: p['id'] for p in patients_resp.data}
        print(f"   - Found {len(patient_map)} patients in master table.")

        # 2. Fetch all cga_records
        print("Fetching cga_records...")
        records_resp = supabase.table("cga_records").select("id, hn, patient_id").execute()
        records = records_resp.data
        print(f"   - Found {len(records)} records to check.")

        # 3. Update records with correct patient_id
        updated_count = 0
        skipped_count = 0
        not_found_count = 0

        for r in records:
            hn = r.get('hn')
            current_pid = r.get('patient_id')
            
            if hn in patient_map:
                correct_pid = patient_map[hn]
                
                # Update only if it's different
                if current_pid != correct_pid:
                    try:
                        supabase.table("cga_records").update({"patient_id": correct_pid}).eq("id", r['id']).execute()
                        updated_count += 1
                        if updated_count % 10 == 0:
                            print(f"   ... updated {updated_count} records")
                    except Exception as e:
                        print(f"   ⚠️ Error updating record ID {r['id']}: {e}")
                else:
                    skipped_count += 1
            else:
                not_found_count += 1

        print("\n✨ Migration Result:")
        print(f"   ✅ Successfully updated: {updated_count} records")
        print(f"   ⏭️ Already correct: {skipped_count} records")
        print(f"   ❌ HN not found in patients: {not_found_count} records")

    except Exception as e:
        print(f"❌ Supabase Error: {e}")

if __name__ == "__main__":
    sync_links()
