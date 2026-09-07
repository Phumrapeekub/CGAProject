from db.db import get_db_connection
import json

try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Check Schema
    cur.execute("DESCRIBE users")
    schema = cur.fetchall()
    
    # Check Data
    cur.execute("SELECT id, username, full_name, role, is_active FROM users WHERE role IN ('doctor', 'nurse') LIMIT 10")
    data = cur.fetchall()
    
    print("SCHEMA:")
    for s in schema:
        print(f"  {s['Field']}: {s['Type']}")
        
    print("\nDATA:")
    for d in data:
        print(f"  {d['username']} (ID:{d['id']}) -> is_active: {d['is_active']} (Type: {type(d['is_active'])})")
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
