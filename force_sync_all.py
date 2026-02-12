import mysql.connector
from db.db import get_db_connection, get_supabase_client
from datetime import date, datetime
from dotenv import load_dotenv
import os

load_dotenv()

def get_cloud_patient_map(supabase):
    """
    สร้างแผนที่แปลง HN -> Cloud ID
    """
    print("🔄 Fetching Cloud Patient Map...")
    mapping = {}
    try:
        # ดึง HN และ ID จาก Cloud ทั้งหมดมาเก็บไว้
        res = supabase.table("patients").select("id, hn").execute()
        for p in res.data:
            if p.get('hn'):
                mapping[str(p['hn'])] = p['id']
        print(f"   Found {len(mapping)} patients in cloud.")
    except Exception as e:
        print(f"   ❌ Error fetching map: {e}")
    return mapping

def sync_all():
    print("🚀 STARTING SMART SYNC (ID REMAPPING MODE)...")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    supabase = get_supabase_client()

    # 1. Sync Patients (Base) - ส่ง HN ไปยืนยันตัวตน
    print("\n📦 Syncing Patients...")
    cur.execute("SELECT * FROM patients")
    patients = cur.fetchall()
    sex_map = {'male': 'ชาย', 'female': 'หญิง'}
    
    for p in patients:
        payload = p.copy()
        if 'id' in payload: del payload['id'] # ตัด Local ID ทิ้ง ให้ Cloud รันเอง
        
        # แปลงข้อมูล
        if 'gender' in payload: 
            payload['sex'] = sex_map.get(payload['gender'], payload['gender'])
        for k, v in payload.items():
            if hasattr(v, 'isoformat'): payload[k] = v.isoformat()
            
        try:
            # ใช้ HN เป็นตัวอ้างอิงหลัก
            supabase.table("patients").upsert(payload, on_conflict="hn").execute()
        except Exception as e:
            if "Could not find" not in str(e): print(f"   ❌ Patient Error ({p.get('hn')}): {e}")

    # 2. สร้าง Map (HN -> Cloud ID) เพื่อใช้เชื่อมโยงตารางอื่น
    cloud_map = get_cloud_patient_map(supabase)

    # 3. Sync Encounters (โดยเปลี่ยน patient_id ให้ตรงกับ Cloud)
    print("\n📦 Syncing Encounters (Remapping IDs)...")
    cur.execute("SELECT e.*, p.hn FROM encounters e JOIN patients p ON e.patient_id = p.id")
    encounters = cur.fetchall()
    
    # Encounter ID Map (Local Enc ID -> Cloud Enc ID)
    enc_map = {} 

    for enc in encounters:
        hn = enc['hn']
        if hn not in cloud_map:
            print(f"   ⚠️ Skip Encounter {enc['id']}: HN {hn} not found in cloud.")
            continue
            
        cloud_p_id = cloud_map[hn]
        payload = {
            "patient_id": cloud_p_id, # ใช้ ID จริงจาก Cloud
            "encounter_date": str(enc['encounter_date']),
            "created_by": enc['created_by']
            # เราจะไม่ส่ง id ของ encounter ไป ให้ Cloud สร้างใหม่หรือใช้อันที่มีถ้า logic ตรงกัน
            # แต่เพื่อความง่ายในการ map ต่อ เราจะลอง search ดูก่อน หรือใช้ upsert แบบระบุ key อื่นถ้ามี
            # ในที่นี้เราจะ insert และจำ ID ใหม่กลับมา (ถ้าทำได้) หรือใช้วิธีค้นหา
        }
        
        # Strategy: ลองค้นหา Encounter ที่มี patient_id + date ตรงกันก่อน
        try:
            exist = supabase.table("encounters").select("id").eq("patient_id", cloud_p_id).eq("encounter_date", str(enc['encounter_date'])).execute()
            if exist.data:
                cloud_enc_id = exist.data[0]['id']
            else:
                # Insert ใหม่
                res = supabase.table("encounters").insert(payload).execute()
                cloud_enc_id = res.data[0]['id']
            
            # จำไว้ใช้กับ Headers
            enc_map[enc['id']] = cloud_enc_id
            
        except Exception as e:
            print(f"   ❌ Enc Error ({enc['id']}): {e}")

    print(f"   Mapped {len(enc_map)} encounters.")

    # 4. Sync CGA Headers (โดยใช้ Encounter ID ใหม่จาก Cloud)
    print("\n📦 Syncing CGA Headers...")
    cur.execute("SELECT * FROM cga_headers WHERE status IN ('completed','sent_to_doctor')")
    headers = cur.fetchall()
    
    for h in headers:
        local_enc_id = h['encounter_id']
        if local_enc_id not in enc_map:
            continue # ไม่มี Encounter แม่ใน Cloud ข้ามไป
            
        cloud_enc_id = enc_map[local_enc_id]
        
        payload = {
            "encounter_id": cloud_enc_id, # ใช้ ID ใหม่
            "risk_level": h['overall_risk'],
            "overall_risk": h['overall_risk'],
            "status": h['status'],
            "assessment_date": str(h['created_at'].date()),
            "is_completed": True
        }
        
        try:
            supabase.table("cga_headers").upsert(payload, on_conflict="encounter_id").execute()
        except Exception as e:
            print(f"   ❌ Header Error (Enc {cloud_enc_id}): {e}")

    print("\n✨ SMART SYNC COMPLETED!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    sync_all()
