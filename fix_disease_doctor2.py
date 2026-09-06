import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

mysql_fetch_code = """        disease_map = {}

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
                      AND a.instrument = 'basic' 
                      AND (a.answer_text LIKE 'chronicDiseases:%' OR a.answer_text LIKE 'otherDisease:%')
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
    '        cga_map = {}',
    '        cga_map = {}\n' + mysql_fetch_code
)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
