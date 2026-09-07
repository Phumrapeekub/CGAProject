import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def check_counts():
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    supabase = create_client(url, key)
    
    p_count = supabase.table("patients").select("id", count="exact").execute().count
    c_count = supabase.table("cga_records").select("id", count="exact").execute().count
    cons_count = supabase.table("consultations").select("id", count="exact").execute().count
    
    print(f"Total Patients: {p_count}")
    print(f"Total CGA Records: {c_count}")
    print(f"Total Consultations: {cons_count}")
    
    cga_data = supabase.table("cga_records").select("hn").execute().data
    pat_data = supabase.table("patients").select("hn").execute().data
    
    cga_hns = {r['hn'] for r in cga_data if r.get('hn')}
    pat_hns = {p['hn'] for p in pat_data if p.get('hn')}
    
    orphans = cga_hns - pat_hns
    print(f"Orphans (CGA but no Patient): {len(orphans)}")
    if orphans:
        print(f"Examples: {list(orphans)[:5]}")

if __name__ == "__main__":
    check_counts()
