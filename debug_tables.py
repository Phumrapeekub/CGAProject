import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = os.getenv("SUPABASE_URL").strip()
    key = os.getenv("SUPABASE_KEY").strip()
    supabase = create_client(url, key)
    
    # Try to see what tables we have by listing some common ones or using a query
    tables = ["consultations", "doctor_notes", "encounters", "cga_records"]
    for t in tables:
        try:
            resp = supabase.table(t).select("*").limit(1).execute()
            print(f"Table '{t}' exists. Columns: {list(resp.data[0].keys()) if resp.data else 'Empty'}")
        except Exception as e:
            print(f"Table '{t}' error or doesn't exist: {e}")

if __name__ == "__main__":
    debug()
