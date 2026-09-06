import sys
sys.stdout.reconfigure(encoding='utf-8')
from db.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM assessment_answers WHERE session_id=184 AND instrument='basic' LIMIT 1")
print(cur.fetchone())
