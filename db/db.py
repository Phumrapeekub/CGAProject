# CGAProject/db/db.py
import os
import mysql.connector


def get_db_connection():
    """
    คืนค่า connection ถ้าเชื่อมได้
    คืนค่า None ถ้าเชื่อมไม่ได้ (กันพัง)
    """

    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "Kantiya203_")
    database = os.getenv("DB_NAME", "cga_system_dev")  # หรือ cga_system_dev

    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
        )
        return conn
    except mysql.connector.Error as err:
        print("❌ DB connect error:", err)
        return None
