import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def check_data():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'cga_system_dev')
        )
        cur = conn.cursor(dictionary=True)
        print("--- Testing Connection OK ---")
        cur.execute("SELECT hn, full_name FROM patients LIMIT 5")
        print("Sample Patients:", cur.fetchall())
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_data()
