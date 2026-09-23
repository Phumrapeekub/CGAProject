import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_supabase_connection() -> dict:
    """
    Attempts to connect to Supabase and performs a basic check.
    Returns a dictionary indicating the connection status and any error messages.
    """
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_key: str = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        return {"status": "error", "message": "SUPABASE_URL environment variable not set."}
    if not supabase_key:
        return {"status": "error", "message": "SUPABASE_KEY environment variable not set."}

    try:
        # Initialize Supabase client
        supabase: Client = create_client(supabase_url, supabase_key)

        # For a more robust check, you might attempt a simple query to a public table.
        # Example:
        # response = supabase.from_('your_public_table_name').select('*').limit(1).execute()
        # if response.data is not None:
        #     return {"status": "success", "message": "Successfully connected to Supabase and performed a test query."}
        # else:
        #     return {"status": "error", "message": f"Supabase client initialized but test query failed: {response.error}"}

        # For now, just successful client initialization is considered a basic check.
        return {"status": "success", "message": "Successfully initialized Supabase client. Remember to run 'pip install supabase-py' first."}

    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to Supabase: {e}"}

def cleanup_stale_tmp_drafts(hours: int = 24) -> dict:
    """
    Deletes abandoned temporary draft records (TMP-xxx with full_name='รอกรอกข้อมูล')
    that were created more than `hours` hours ago, preventing database clutter.
    """
    from datetime import datetime, timedelta
    from db.db import get_supabase_client
    try:
        supabase = get_supabase_client()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        # 1. Search for abandoned draft patients
        res = supabase.table("patients").select("id, hn").like("hn", "TMP-%").eq("full_name", "รอกรอกข้อมูล").lte("created_at", cutoff).execute()
        stale_patients = res.data or []
        if not stale_patients:
            return {"status": "success", "deleted_count": 0, "message": "No stale TMP drafts found."}
            
        p_ids = [p["id"] for p in stale_patients]
        hns = [p["hn"] for p in stale_patients]
        
        # 2. Delete associated records, headers, encounters
        res_e = supabase.table("encounters").select("id").in_("patient_id", p_ids).execute()
        if res_e.data:
            e_ids = [e["id"] for e in res_e.data]
            supabase.table("cga_records").delete().in_("encounter_id", e_ids).execute()
            supabase.table("cga_headers").delete().in_("encounter_id", e_ids).execute()
            supabase.table("encounters").delete().in_("id", e_ids).execute()
            
        supabase.table("cga_records").delete().in_("hn", hns).execute()
        supabase.table("patients").delete().in_("id", p_ids).execute()
        
        print(f"[CLEANUP] Deleted {len(p_ids)} stale TMP- drafts older than {hours}h.")
        return {"status": "success", "deleted_count": len(p_ids)}
    except Exception as e:
        print(f"[CLEANUP ERROR] {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    result = check_supabase_connection()
    print(f"Supabase Connection Check: {result['status'].upper()}")
    print(f"Message: {result['message']}")
    cleanup_res = cleanup_stale_tmp_drafts(24)
    print(f"Cleanup Result: {cleanup_res}")
