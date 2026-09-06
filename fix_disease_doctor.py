import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add get_db_connection import
if 'from db.db import get_db_connection' not in content:
    content = content.replace(
        'from db.db import get_db_client',
        'from db.db import get_db_client, get_db_connection'
    )

# Inject MySQL disease fetching before the main loop
mysql_fetch_code = """
        cga_map = {}
        consult_map = {}
        disease_map = {}

        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            if hns:
                format_strings = ','.join(['%s'] * len(hns))
                query_sql = f'''
                    SELECT p.hn, a.answer_text
                    FROM patients p
                    JOIN encounters e ON p.id = e.patient_id
                    JOIN assessment_answers a ON e.session_id = a.session_id
                    WHERE p.hn IN ({format_strings})
                      AND a.instrument = "basic" 
                      AND (a.answer_text LIKE "chronicDiseases:%%" OR a.answer_text LIKE "otherDisease:%%")
                '''
                cur.execute(query_sql, tuple(hns))
                for mr in cur.fetchall():
                    mhn = mr['hn']
                    ans = mr['answer_text']
                    if ':' in ans:
                        _, v = ans.split(':', 1)
                        if v.strip() and v.strip() != '-':
                            if mhn not in disease_map:
                                disease_map[mhn] = []
                            disease_map[mhn].append(v.strip())
            cur.close()
            conn.close()
        except Exception as e:
            print(f"DEBUG: MySQL disease fetch error: {e}")
"""

content = content.replace(
    '        cga_map = {}\n        consult_map = {}',
    mysql_fetch_code
)

# Update disease mapping logic
new_disease_logic = """
            # Map Columns: Fallback between cga_records, MySQL, and consultations
            d_list = disease_map.get(curr_hn)
            if d_list:
                disease = ", ".join(d_list)
            else:
                disease = cons.get("note_from_nurse") or "-"
"""

content = content.replace(
    '            # Map Columns: Fallback between cga_records and consultations\n            disease = r.get("chronic_disease") or cons.get("note_from_nurse") or "-"',
    new_disease_logic
)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
