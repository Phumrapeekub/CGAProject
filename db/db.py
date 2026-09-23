import os
import mysql.connector
from supabase import create_client, Client

def get_db_connection():
    """
    Returns a MySQL connection with robust fallbacks:
    1. Local unix socket (/tmp/mysql.sock)
    2. TCP connection (127.0.0.1:3306 or DB_HOST)
    """
    # 1. First priority on Linux container: Local Unix Socket
    for sock in ["/tmp/mysql.sock", "/app/mariadb/run/mysql.sock", "/var/run/mysqld/mysqld.sock"]:
        if os.path.exists(sock):
            for pwd in ["Kantiya203_", "", None]:
                try:
                    conn = mysql.connector.connect(
                        unix_socket=sock,
                        user="root",
                        password=pwd,
                        database="cga_system_dev",
                        connect_timeout=3
                    )
                    return conn
                except mysql.connector.Error:
                    continue

    # 2. Second priority: TCP connection
    host = os.getenv("DB_HOST", "127.0.0.1")
    hosts_to_try = [host]
    if host not in ["127.0.0.1", "localhost"]:
        hosts_to_try.append("127.0.0.1")
    
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "root")
    default_pw = os.getenv("DB_PASSWORD") or "Kantiya203_"
    database = os.getenv("DB_NAME", "cga_system_dev")

    for h in hosts_to_try:
        p = port if h == host else 3306
        u = user if h == host else "root"
        d = database if h == host else "cga_system_dev"
        for ssl_mode in [False, True]:
            for pwd in [default_pw, "Kantiya203_", "", None]:
                try:
                    conn = mysql.connector.connect(
                        host=h,
                        port=p,
                        user=u,
                        password=pwd,
                        database=d,
                        ssl_disabled=ssl_mode,
                        connect_timeout=3
                    )
                    return conn
                except mysql.connector.Error:
                    continue

    print(f"DB connect error: Unable to connect to MySQL")
    return None

def get_supabase_client() -> Client:
    """
    Returns a Supabase client
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

get_db_client = get_supabase_client
