import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def check_data_integrity():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    supabase = create_client(url, key)

    print("--- Checking Data Integrity ---")
    
    # 1. ลองดึงข้อมูลแบบ Join
    print("\nAttempting Join Query...")
    try:
        res = supabase.table("cga_headers").select("id, assessed_at, encounters(id, patient_id)").limit(5).execute()
        print(f"Fetch Successful: {len(res.data)} records found.")
        for row in res.data:
            print(row)
    except Exception as e:
        print(f"Query Failed: {e}")

    # 2. ตรวจสอบจำนวนแถวในแต่ละตาราง
    print("\nTable counts:")
    for table in ["patients", "encounters", "cga_headers"]:
        count = supabase.table(table).select("count", count="exact").execute().count
        print(f"{table}: {count} rows")

if __name__ == "__main__":
    check_data_integrity()