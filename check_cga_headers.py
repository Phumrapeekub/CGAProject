import mysql.connector

def check():
    config = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'Kantiya203_',
        'database': 'cga_system_dev'
    }
    try:
        conn = mysql.connector.connect(**config)
        cur = conn.cursor(dictionary=True)
        print("Latest 10 records in local 'cga_headers':")
        cur.execute("SELECT * FROM cga_headers ORDER BY created_at DESC LIMIT 10")
        for row in cur.fetchall():
            print(row)
        conn.close()
    except Exception as e:
        print(e)

if __name__ == "__main__":
    check()
