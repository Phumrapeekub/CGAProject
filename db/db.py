import os
import mysql.connector
from supabase import create_client, Client

def get_db_connection():
    """
    Returns a MySQL connection using environment variables with robust fallbacks
    """
    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    default_pw = os.getenv("DB_PASSWORD") or "Kantiya203_"
    database = os.getenv("DB_NAME", "cga_system_dev")
    port = int(os.getenv("DB_PORT", "3306"))

    # 1. Try TCP connection with SSL False (for Cloud DBs like Aiven) and True (for local)
    passwords_to_try = [default_pw]
    if default_pw != "Kantiya203_":
        passwords_to_try.append("Kantiya203_")
    passwords_to_try.extend(["", None])

    for ssl_mode in [False, True]:
        for pwd in passwords_to_try:
            try:
                conn = mysql.connector.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=pwd,
                    database=database,
                    ssl_disabled=ssl_mode,
                    connect_timeout=4
                )
                return conn
            except mysql.connector.Error:
                continue

    # 2. Try Unix Sockets if available on Linux
    for sock in ["/app/mariadb/run/mysql.sock", "/var/run/mysqld/mysqld.sock", "/tmp/mysqld/mysqld.sock", "/tmp/mysql.sock"]:
        if os.path.exists(sock):
            for pwd in passwords_to_try:
                try:
                    conn = mysql.connector.connect(
                        unix_socket=sock,
                        user=user,
                        password=pwd,
                        database=database,
                        connect_timeout=3
                    )
                    return conn
                except mysql.connector.Error:
                    continue

    print("DB connect error: Unable to connect to MySQL on host or socket")
    return None

def get_supabase_client() -> Client:
    """
    Returns a Supabase client
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

get_db_client = get_supabase_client
