import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """        latest_session_id = latest_cga.get("session_id") or latest_c.get("session_id")
        print(f"DEBUG: patient_detail HN={hn} latest_session_id={latest_session_id}")
        
        if latest_session_id:
            try:
                # A) Detailed answers
                res_ans = supabase.table("assessment_answers").select("*").eq("session_id", latest_session_id).execute()
                print(f"DEBUG: Fetched {len(res_ans.data or [])} answers for session {latest_session_id}")
                for row in (res_ans.data or []):"""

new_logic = """        # Retrieve latest_session_id from local DB if available
        latest_session_id = None
        ans_rows = []
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            if encounter_id:
                cur.execute("SELECT id FROM assessment_sessions WHERE encounter_id=%s ORDER BY id DESC LIMIT 1", (encounter_id,))
                sess_row = cur.fetchone()
                if sess_row:
                    latest_session_id = sess_row['id']
                    cur.execute("SELECT * FROM assessment_answers WHERE session_id=%s", (latest_session_id,))
                    ans_rows = cur.fetchall()
            conn.close()
        except:
            pass

        print(f"DEBUG: patient_detail HN={hn} latest_session_id={latest_session_id}")
        
        if latest_session_id and ans_rows:
            try:
                # A) Detailed answers
                print(f"DEBUG: Fetched {len(ans_rows)} answers for session {latest_session_id} from Local DB")
                for row in ans_rows:"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
