import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not url or not key:
        print("Settings missing")
        return

    try:
        supabase = create_client(url, key)
        resp = supabase.table("consultations").select("*").limit(5).execute()
        if resp.data:
            print("SAMPLE CONSULTATIONS:")
            for item in resp.data:
                print(f"HN: {item.get('hn')}, Doctor: {item.get('doctor_id')}, DrName: {item.get('doctor_name')}, CreatedAt: {item.get('created_at')}")
            print("\nALL COLUMNS IN FIRST RECORD:")
            print(list(resp.data[0].keys()))
        else:
            print("No data found in consultations table.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug()
