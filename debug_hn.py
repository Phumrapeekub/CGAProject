import mysql.connector

def debug_hn():
    config = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'Kantiya203_',
        'database': 'cga_system_dev'
    }
    try:
        conn = mysql.connector.connect(**config)
        cur = conn.cursor(dictionary=True)
        print("Checking for suspicious HNs...")
        cur.execute("SELECT id, hn, full_name FROM patients WHERE hn LIKE '%1844674407%' OR LENGTH(hn) > 10")
        rows = cur.fetchall()
        for r in rows:
            print(r)
        
        print("\nLatest 5 patients:")
        cur.execute("SELECT id, hn, full_name FROM patients ORDER BY id DESC LIMIT 5")
        for r in cur.fetchall():
            print(r)
            
        conn.close()
    except Exception as e:
        print(e)

if __name__ == "__main__":
    debug_hn()