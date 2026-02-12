import mysql.connector
import re

def fix_corrupted_hns():
    config = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'Kantiya203_',
        'database': 'cga_system_dev'
    }
    try:
        conn = mysql.connector.connect(**config)
        cur = conn.cursor(dictionary=True)
        
        # 1. Find Max Good HN
        print("Finding current maximum valid HN...")
        cur.execute("SELECT hn FROM patients WHERE hn LIKE 'HN%'")
        max_num = 0
        pattern = re.compile(r'^HN(\d+)$', re.IGNORECASE)
        for r in cur.fetchall():
            m = pattern.match(str(r['hn']))
            if m:
                val = int(m.group(1))
                if val < 1000000 and val > max_num:
                    max_num = val
        
        print(f"Current valid max HN: HN{max_num:03d}")
        
        # 2. Find Corrupted HNs
        cur.execute("SELECT id, hn, full_name FROM patients WHERE hn LIKE 'HN1844674407%'")
        corrupted = cur.fetchall()
        
        if not corrupted:
            print("No corrupted HNs found starting with 'HN1844674407'.")
        else:
            print(f"Found {len(corrupted)} corrupted records. Fixing...")
            for row in corrupted:
                max_num += 1
                new_hn = f"HN{max_num:03d}"
                print(f"  Fixing ID {row['id']}: {row['hn']} -> {new_hn} ({row['full_name']})")
                cur.execute("UPDATE patients SET hn = %s WHERE id = %s", (new_hn, row['id']))
            
            conn.commit()
            print("✅ All HNs have been normalized.")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_corrupted_hns()