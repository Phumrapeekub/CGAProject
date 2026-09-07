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
        
        print("--- ตรวจสอบตาราง Patients ---")
        cur.execute("SELECT hn, full_name FROM patients WHERE hn LIKE '%57%' OR hn LIKE '%58%' OR hn LIKE '%59%' OR hn LIKE '%60%'")
        patients = cur.fetchall()
        for p in patients:
            print(f"Master Patient -> HN: {p['hn']} | Name: {p['full_name']}")
            
        print("
--- ตรวจสอบตาราง stg_cga_csv (ประวัติการประเมิน) ---")
        cur.execute("SELECT hn, first_name, last_name FROM stg_cga_csv WHERE hn LIKE '%57%' OR hn LIKE '%58%' OR hn LIKE '%59%' OR hn LIKE '%60%'")
        history = cur.fetchall()
        for h in history:
            print(f"Assessment History -> HN: {h['hn']} | Name: {h['first_name']} {h['last_name']}")
            
        if not history:
            print("!!! ไม่พบข้อมูลการประเมินของ HN 57-60 ในตารางประวัติ !!!")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_data()
