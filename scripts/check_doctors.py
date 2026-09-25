import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def debug():
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    supabase = create_client(url, key)
    
    try:
        resp = supabase.table("users").select("id, username, role").eq("role", "doctor").execute()
        print("DOCTORS IN SYSTEM:")
        for d in resp.data:
            print(f"ID: {d['id']}, Username: {d['username']}")
            
        resp2 = supabase.table("encounters").select("id, assigned_doctor_id").execute()
        print("\nENCOUNTERS AND ASSIGNED DOCTORS:")
        for e in resp2.data:
            print(f"EncID: {e['id']}, DocID: {e['assigned_doctor_id']}")
    except Exception as ex:
        print(f"Error: {ex}")

if __name__ == "__main__":
    debug()
