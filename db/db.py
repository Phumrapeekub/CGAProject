import os
import mysql.connector
from supabase import create_client, Client

def get_db_connection():
    """
    Returns a MySQL connection using environment variables
    """
    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD")
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
        print("DB connect error:", err)
        return None

def get_supabase_client() -> Client:
    """
    Returns a Supabase client
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

get_db_client = get_supabase_client
