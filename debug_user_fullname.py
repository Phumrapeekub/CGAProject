import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

def check_nurse_fullname():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password=os.getenv("DB_PASSWORD", "Siriyakorn05_"), # Fallback password from context
            database="cga_system_dev", # Assuming dev db
            port=3306
        )
        cur = conn.cursor(dictionary=True)
        
        username = "nurse1"
        cur.execute("SELECT id, username, full_name FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        if user:
            print(f"✅ Found User: {user['username']}")
            print(f"   Full Name (Raw): '{user['full_name']}'")
            if not user['full_name']:
                print("   ⚠️ Full Name is Empty/Null!")
            else:
                print("   ✅ Full Name exists.")
        else:
            print(f"❌ User '{username}' not found.")
            
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_nurse_fullname()
