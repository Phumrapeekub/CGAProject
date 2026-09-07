
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def sync_encounters():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found.")
        return

    supabase = create_client(url, key)

    print("--- Starting Encounters Sync ---")

    # 1. ดึงรายชื่อผู้ป่วยทั้งหมด (สร้างเป็น Dictionary สำหรับการค้นหาที่รวดเร็ว)
    # เก็บทั้ง id และ hn เผื่อกรณีมีการสลับกัน
    pat_resp = supabase.table("patients").select("id, hn").execute()
    patients_by_id = {p['id']: p['hn'] for p in pat_resp.data}
    patients_by_hn = {p['hn']: p['id'] for p in pat_resp.data}

    # 2. ดึงข้อมูลการตรวจ (Encounters) ทั้งหมด
    enc_resp = supabase.table("encounters").select("*").execute()
    encounters = enc_resp.data

    print(f"Checking {len(encounters)} encounter records...")

    deleted_count = 0
    valid_count = 0

    for enc in encounters:
        p_id = enc.get('patient_id')
        
        # ตรวจสอบว่า patient_id นี้มีอยู่ในตาราง patients หรือไม่
        if p_id in patients_by_id:
            valid_count += 1
            continue # ข้อมูลถูกต้องแล้ว ข้ามไป
        
        # ถ้าไม่มี ลองเช็คว่ามันเป็น HN ที่หลงมาหรือไม่
        # (บางครั้งโปรแกรมอาจจะเผลอใส่ HN ลงในช่อง ID)
        if str(p_id) in patients_by_hn:
            actual_id = patients_by_hn[str(p_id)]
            print(f"Fixing encounter ID {enc['id']}: Mapping HN {p_id} to actual ID {actual_id}")
            supabase.table("encounters").update({"patient_id": actual_id}).eq("id", enc['id']).execute()
            valid_count += 1
        else:
            # ถ้าหาไม่เจอจริงๆ ให้ลบออก เพราะจะทำให้หน้าเว็บพัง
            print(f"Deleting orphaned encounter ID {enc['id']} (Patient ID {p_id} not found)")
            
            # ก่อนลบ encounter ต้องลบข้อมูลที่ระบุไปถึงมันก่อน (CGA Headers, etc.)
            try:
                supabase.table("cga_headers").delete().eq("encounter_id", enc['id']).execute()
                supabase.table("assessment_sessions").delete().eq("encounter_id", enc['id']).execute()
                supabase.table("encounters").delete().eq("id", enc['id']).execute()
                deleted_count += 1
            except Exception as e:
                print(f"Could not delete encounter {enc['id']}: {e}")

    print(f"Sync complete. Valid/Fixed: {valid_count}, Deleted: {deleted_count}")

if __name__ == "__main__":
    sync_encounters()
