
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def cleanup_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    print("--- Starting Cleanup Process ---")

    # 1. ค้นหาผู้ป่วยที่ HN ไม่เป็นไปตามรูปแบบ 'HN%'
    # เราจะหาคนที่ไม่เข้าพวก
    try:
        all_patients = supabase.table("patients").select("id, hn").execute().data
        to_delete_ids = [p['id'] for p in all_patients if not str(p['hn']).startswith('HN')]
        
        if not to_delete_ids:
            print("No invalid HN records found.")
            return

        print(f"Found {len(to_delete_ids)} records to remove: {to_delete_ids}")

        # 2. เริ่มลบข้อมูลที่เกี่ยวข้อง (Dependencies)
        # ขั้นตอนต้องเรียงลำดับเพื่อไม่ให้ติด Foreign Key
        
        # ก. ลบจากตารางย่อยที่สุดก่อน (Scores)
        # ต้องหา cga_id ที่เชื่อมกับคนไข้เหล่านี้
        enc_resp = supabase.table("encounters").select("id").in_("patient_id", to_delete_ids).execute()
        enc_ids = [e['id'] for e in enc_resp.data]
        
        if enc_ids:
            cga_resp = supabase.table("cga_headers").select("id").in_("encounter_id", enc_ids).execute()
            cga_ids = [c['id'] for c in cga_resp.data]
            
            if cga_ids:
                print(f"Deleting scores for {len(cga_ids)} CGA headers...")
                supabase.table("assessment_scores").delete().in_("cga_id", cga_ids).execute()
                print("Deleting CGA headers...")
                supabase.table("cga_headers").delete().in_("id", cga_ids).execute()

            print("Deleting assessment sessions...")
            supabase.table("assessment_sessions").delete().in_("encounter_id", enc_ids).execute()
            
            print("Deleting encounters...")
            supabase.table("encounters").delete().in_("id", enc_ids).execute()

        # ข. ลบการนัดหมาย
        print("Deleting appointments...")
        supabase.table("appointments").delete().in_("patient_id", to_delete_ids).execute()

        # ค. ลบตัวผู้ป่วยเอง
        print("Deleting patient records...")
        supabase.table("patients").delete().in_("id", to_delete_ids).execute()

        print("--- Cleanup Finished Successfully ---")

    except Exception as e:
        print(f"An error occurred during cleanup: {e}")

if __name__ == "__main__":
    cleanup_supabase()
