from db.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM assessment_answers WHERE instrument='basic'")
for r in cur.fetchall():
    print(r['answer_text'])
