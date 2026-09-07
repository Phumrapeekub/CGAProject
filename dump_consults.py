import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    supabase = create_client(url, key)
    
    resp = supabase.table("consultations").select("*").execute()
    print(f"Checking {len(resp.data)} consultation records...")
    for r in resp.data:
        print(r)

if __name__ == "__main__":
    debug()
