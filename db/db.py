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
    Connects to local unix socket or localhost TCP, auto-creating cga_system_dev if needed.
    """
    # 1. Local unix socket
    for sock in ["/tmp/mysql.sock", "/app/mariadb/run/mysql.sock", "/var/run/mysqld/mysqld.sock"]:
        if os.path.exists(sock):
            for u in ["root", "user"]:
                for pwd in ["Kantiya203_", "", None]:
                    try:
                        conn = mysql.connector.connect(
                            unix_socket=sock,
                            user=u,
                            password=pwd,
                            database="cga_system_dev",
                            connect_timeout=1
                        )
                        return conn
                    except mysql.connector.Error as e:
                        if e.errno == 1049:  # Unknown database
                            try:
                                admin_c = mysql.connector.connect(unix_socket=sock, user=u, password=pwd, connect_timeout=1)
                                admin_cur = admin_c.cursor()
                                admin_cur.execute("CREATE DATABASE IF NOT EXISTS cga_system_dev")
                                admin_cur.close()
                                admin_c.close()
                                return mysql.connector.connect(unix_socket=sock, user=u, password=pwd, database="cga_system_dev", connect_timeout=1)
                            except:
                                pass
                        continue

    # 2. Localhost TCP (always try 127.0.0.1:3306 first)
    for h in ["127.0.0.1", "localhost"]:
        for port in [3306]:
            for u in ["root", "user"]:
                for pwd in ["Kantiya203_", "", None]:
                    try:
                        conn = mysql.connector.connect(
                            host=h,
                            port=port,
                            user=u,
                            password=pwd,
                            database="cga_system_dev",
                            connect_timeout=1
                        )
                        return conn
                    except mysql.connector.Error as e:
                        if e.errno == 1049:  # Unknown database
                            try:
                                admin_c = mysql.connector.connect(host=h, port=port, user=u, password=pwd, connect_timeout=1)
                                admin_cur = admin_c.cursor()
                                admin_cur.execute("CREATE DATABASE IF NOT EXISTS cga_system_dev")
                                admin_cur.close()
                                admin_c.close()
                                return mysql.connector.connect(host=h, port=port, user=u, password=pwd, database="cga_system_dev", connect_timeout=1)
                            except:
                                pass
                        pass

    return None


