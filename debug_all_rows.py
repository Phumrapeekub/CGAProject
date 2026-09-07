import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = os.getenv("SUPABASE_URL").strip()
    key = os.getenv("SUPABASE_KEY").strip()
    supabase = create_client(url, key)
    
    resp = supabase.table("consultations").select("*").execute()
    print(f"Found {len(resp.data)} records in consultations.")
    all_keys = set()
    for r in resp.data:
        for k in r.keys():
            all_keys.add(k)
    print(f"All unique columns found in table: {list(all_keys)}")
    
    # Also check doctor_notes
    resp2 = supabase.table("doctor_notes").select("*").execute()
    print(f"Found {len(resp2.data)} records in doctor_notes.")
    if resp2.data:
        print(f"Sample doctor_note: {resp2.data[0]}")

if __name__ == "__main__":
    debug()
