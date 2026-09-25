import mysql.connector
from db.db import get_db_connection, get_supabase_client
from datetime import date

def force_sync_headers():
    print("🔄 Starting Force Sync for CGA Headers...")
    local_conn = get_db_connection()
    cur = local_conn.cursor(dictionary=True)
    supabase = get_supabase_client()

    try:
        # ดึงข้อมูลสรุปจากเครื่องที่มีสถานะ completed หรือ sent_to_doctor
        cur.execute("""
            SELECT h.encounter_id, h.overall_risk, h.status, h.created_at, e.created_by
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            WHERE h.status IN ('completed', 'sent_to_doctor')
        """)
        headers = cur.fetchall()
        print(f"Found {len(headers)} completed assessments in local DB.")

        for h in headers:
            risk = h['overall_risk'] or 'low'
            payload = {
                "encounter_id": h['encounter_id'],
                "risk_level": risk,
                "overall_risk": risk,
                "status": h['status'],
                "assessment_date": str(h['created_at'].date()),
                "is_completed": True
            }
            print(f"  -> Syncing Encounter {h['encounter_id']} (Risk: {risk})...", end="")
            try:
                # ลอง Insert ตรงๆ ไม่ใช้ Upsert เพื่อดู Error จริงๆ
                res = supabase.table("cga_headers").upsert(payload, on_conflict="encounter_id").execute()
                print(" ✅ Success")
            except Exception as sb_err:
                print(f" ❌ Failed: {sb_err}")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
    finally:
        cur.close()
        local_conn.close()

if __name__ == "__main__":
    force_sync_headers()
