import os
import mysql.connector
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    """
    Returns a cached Supabase client
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL", "https://ylahheyefrqxcjqccpsn.supabase.co")
    key = os.getenv("SUPABASE_KEY", "sb_publishable_w4aFFHRYgyZEtzhM0Pxq1g_YWtCqIHJ")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment")

    _supabase_client = create_client(url, key)
    return _supabase_client

get_db_client = get_supabase_client

def get_db_connection():
    """
    Safe fallback for MySQL connection:
    Only attempts local connection if available, never hangs on unreachable cloud hosts.
    """
    # 1. Local unix socket
    for sock in ["/tmp/mysql.sock", "/app/mariadb/run/mysql.sock", "/var/run/mysqld/mysqld.sock"]:
        if os.path.exists(sock):
            for pwd in ["Kantiya203_", "", None]:
                try:
                    conn = mysql.connector.connect(
                        unix_socket=sock,
                        user="root",
                        password=pwd,
                        database="cga_system_dev",
                        connect_timeout=1
                    )
                    return conn
                except mysql.connector.Error:
                    continue

    # 2. Localhost TCP (only 127.0.0.1 or localhost, never remote dead hosts)
    host = os.getenv("DB_HOST", "127.0.0.1")
    if host in ["127.0.0.1", "localhost"]:
        port = int(os.getenv("DB_PORT", "3306"))
        user = os.getenv("DB_USER", "root")
        pwd = os.getenv("DB_PASSWORD") or "Kantiya203_"
        database = os.getenv("DB_NAME", "cga_system_dev")
        try:
            conn = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=pwd,
                database=database,
                connect_timeout=1
            )
            return conn
        except mysql.connector.Error:
            pass

    return None

