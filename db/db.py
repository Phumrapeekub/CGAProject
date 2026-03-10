# CGAProject/db/db.py
import os
import mysql.connector
from supabase import create_client, Client

def get_db_connection():
    """
    คืนค่า connection ของ MySQL ถ้าเชื่อมได้
    """
    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "Kantiya203_")
    database = os.getenv("DB_NAME", "cga_system_dev")
    port = os.getenv("DB_PORT", "3306")

    try:
        conn = mysql.connector.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            ssl_disabled=True
        )
        return conn
    except mysql.connector.Error as err:
        print("❌ DB connect error:", err)
        return None

def get_supabase_client() -> Client:
    """
    คืนค่า Supabase client
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)
