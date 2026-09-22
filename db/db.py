# CGAProject/db/db.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client

# Singleton to avoid recreating the client multiple times
_supabase_client = None

def get_db_client():
    """
    Initialize and return Supabase client
    """
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            print("⚠️ SUPABASE_URL or SUPABASE_ANON_KEY not found in environment")
            return None
        _supabase_client = create_client(url, key)
    return _supabase_client

def get_db_connection():
    """
    คืนค่า connection ถ้าเชื่อมได้ (PostgreSQL)
    คืนค่า None ถ้าเชื่อมไม่ได้
    """
    host = (os.getenv("DB_HOST") or "127.0.0.1").strip()
    user = (os.getenv("DB_USER") or "postgres").strip()
    password = (os.getenv("DB_PASSWORD") or "").strip()
    database = (os.getenv("DB_NAME") or "postgres").strip()
    port = (os.getenv("DB_PORT") or "6543").strip()

    try:
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=database,
            port=port,
            connect_timeout=10
        )
        return conn
    except Exception as err:
        print(f"❌ DB connect error (Host: {host}, Port: {port}):", err)
        return None
