import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = os.getenv("SUPABASE_URL").strip()
    key = os.getenv("SUPABASE_KEY").strip()
    supabase = create_client(url, key)
    
    try:
        # In Supabase/PostgreSQL, we can query the information_schema
        # But with the SDK, we might just try common names
        test_names = ["consultation", "consultations", "consults", "doctor_consultations"]
        for name in test_names:
            try:
                resp = supabase.table(name).select("*", count="exact").limit(1).execute()
                print(f"Table '{name}' exists with {resp.count} rows.")
                if resp.data:
                    print(f"  Columns: {list(resp.data[0].keys())}")
            except:
                pass
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug()
