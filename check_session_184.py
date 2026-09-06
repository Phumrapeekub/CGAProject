import sys
sys.stdout.reconfigure(encoding='utf-8')
from db.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM assessment_answers WHERE session_id=184 AND instrument='basic'")
for r in cur.fetchall():
    print(r['answer_text'])
