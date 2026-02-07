import os
import mysql.connector
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def migrate():
    print("🚀 Starting Migration to Supabase via API SDK...")

    # 1. Connect to Local MySQL
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    try:
        mysql_conn = mysql.connector.connect(
            host=db_host,
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "cga_system_dev")
        )
        mysql_cur = mysql_conn.cursor(dictionary=True)
        print("✅ Connected to Local MySQL")
    except Exception as e:
        print(f"❌ MySQL Connection Error: {e}")
        return

    # 2. Connect to Supabase API
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("✅ Connected to Supabase API")
    except Exception as e:
        print(f"❌ Supabase SDK Error: {e}")
        return

    # 3. Migrate Users
    print("Migrating users...")
    try:
        mysql_cur.execute("SELECT * FROM users")
        users = mysql_cur.fetchall()
        for u in users:
            # Prepare data
            data = {
                "id": u['id'],
                "username": u['username'],
                "password_hash": u['password_hash'],
                "full_name": u['full_name'],
                "role": u['role'],
                "is_active": bool(u['is_active'])
            }
            # Upsert via SDK
            supabase.table("users").upsert(data).execute()
        print(f"   - Processed {len(users)} users.")
    except Exception as e:
        print(f"   ⚠️ Error migrating users: {e}")

    # 4. Migrate Patients
    print("Migrating patients...")
    try:
        mysql_cur.execute("SELECT * FROM patients")
        patients = mysql_cur.fetchall()
        for p in patients:
            data = {
                "id": p['id'],
                "hn": p['hn'],
                "full_name": p['full_name'],
                "gender": p['gender'],
                "birth_date": str(p['birth_date']) if p['birth_date'] else None,
                "phone": p['phone'],
                "address": p['address']
            }
            supabase.table("patients").upsert(data).execute()
        print(f"   - Processed {len(patients)} patients.")
    except Exception as e:
        print(f"   ⚠️ Error migrating patients: {e}")

    print("\n✅ Migration via API Complete!")

    mysql_cur.close()
    mysql_conn.close()

if __name__ == "__main__":
    migrate()