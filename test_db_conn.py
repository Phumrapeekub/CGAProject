import os
from dotenv import load_dotenv
import psycopg2

load_dotenv(override=True)

def test_conn():
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")
    port = os.getenv("DB_PORT")
    
    print(f"Testing connection to {host}:{port} as {user}...")
    try:
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=database,
            port=port,
            connect_timeout=10
        )
        print("✅ Connection successful!")
        cur = conn.cursor()
        cur.execute("SELECT version();")
        print(f"PostgreSQL version: {cur.fetchone()[0]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_conn()
