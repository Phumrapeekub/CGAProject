# CGAProject/db/db.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    คืนค่า Supabase Client แทน Connection ดั้งเดิม
    """
    url: str = os.getenv("SUPABASE_URL")
    key: str = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
        return None

    try:
        supabase: Client = create_client(url, key)
        return supabase
    except Exception as err:
        print("❌ Supabase API connect error:", err)
        return None
