import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: cga_general phone
old_cga = """        cga_general = {
            "caregiver_name": latest_cga.get("caregiver_name") or latest_c.get("caregiver_name") or "-", 
            "caregiver_phone": latest_cga.get("phone") or latest_c.get("caregiver_phone") or "-",
            "caregiver_relation": latest_c.get("caregiver_relation") or "-","""
new_cga = """        cga_general = {
            "caregiver_name": latest_cga.get("caregiver_name") or latest_c.get("caregiver_name") or "-", 
            "caregiver_phone": latest_cga.get("emergency_phone") or latest_c.get("caregiver_phone") or "-",
            "caregiver_relation": latest_c.get("caregiver_relation") or "-","""
content = content.replace(old_cga, new_cga)


# Fix 2: Add temp vars for basic answers before mmse_details
old_details = """        mmse_details = {}
        tgds_details = {}
        q8_details = {}"""
new_details = """        mmse_details = {}
        tgds_details = {}
        q8_details = {}
        twoq_details = {}
        basic_extras = {}"""
content = content.replace(old_details, new_details)


# Fix 3: Fetch from Local DB instead of Supabase
old_session = """        latest_session_id = latest_cga.get("session_id") or latest_c.get("session_id")
        print(f"DEBUG: patient_detail HN={hn} latest_session_id={latest_session_id}")
        
        if latest_session_id:
            try:
                # A) Detailed answers
                res_ans = supabase.table("assessment_answers").select("*").eq("session_id", latest_session_id).execute()
                print(f"DEBUG: Fetched {len(res_ans.data or [])} answers for session {latest_session_id}")
                for row in (res_ans.data or []):
                    inst = str(row.get("instrument") or "").lower()
                    q_no = row.get("question_no")
                    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")
                    
                    if inst == "mmse":"""
new_session = """        # Fetch session_id from Local DB
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
                print(f"DEBUG: Fetched {len(ans_rows)} answers for session {latest_session_id} from Local DB")
                for row in ans_rows:
                    inst = str(row.get("instrument") or "").lower()
                    q_no = row.get("question_no")
                    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")
                    
                    if inst == "mmse":"""
content = content.replace(old_session, new_session)


# Fix 4: Add basic parsing to loop and define txt early
old_loop = """                    if inst == "mmse":
                        # Map to keys expected by mmse_form_partial.html
                        # e.g. q1_time_score, q2_place_score, etc.
                        if q_no == 1: mmse_details["q1_time_score"] = row.get("score")
                        elif q_no == 2: mmse_details["q2_place_score"] = row.get("score")
                        elif q_no == 3: mmse_details["q3_registration_score"] = row.get("score")
                        elif q_no == 4: mmse_details["q4_attention_calc_score"] = row.get("score")
                        elif q_no == 5: mmse_details["q5_recall_score"] = row.get("score")
                        elif q_no == 6: mmse_details["q6_naming_score"] = row.get("score")
                        elif q_no == 7: mmse_details["q7_repetition_score"] = row.get("score")
                        
                        # Handle individual tags if they were saved in answer_text (like 'q1_1')
                        txt = str(row.get("answer_text") or "").lower()
                        if "_" in txt: mmse_details[txt] = row.get("score")
                elif inst == "tgds":"""
new_loop = """                    txt = str(row.get("answer_text") or "").lower()
                    if inst == "mmse":
                        # Map to keys expected by mmse_form_partial.html
                        # e.g. q1_time_score, q2_place_score, etc.
                        if q_no == 1: mmse_details["q1_time_score"] = row.get("score")
                        elif q_no == 2: mmse_details["q2_place_score"] = row.get("score")
                        elif q_no == 3: mmse_details["q3_registration_score"] = row.get("score")
                        elif q_no == 4: mmse_details["q4_attention_calc_score"] = row.get("score")
                        elif q_no == 5: mmse_details["q5_recall_score"] = row.get("score")
                        elif q_no == 6: mmse_details["q6_naming_score"] = row.get("score")
                        elif q_no == 7: mmse_details["q7_repetition_score"] = row.get("score")
                        
                        # Handle individual tags if they were saved in answer_text (like 'q1_1')
                        if "_" in txt: mmse_details[txt] = row.get("score")
                elif inst == "tgds":"""
content = content.replace(old_loop, new_loop)


# Fix 5: Append basic parsing block
old_end_loop = """                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"

        # 3) Prepare Score Objects for Template"""
new_end_loop = """                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"
                elif inst == "basic":
                    if val and isinstance(val, str):
                        if val.startswith("live:"):
                            l = val.split(":", 1)[1]
                            basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                        elif val.startswith("height:"):
                            basic_extras["height"] = val.split(":", 1)[1]
                        elif val.startswith("waist:"):
                            basic_extras["waist"] = val.split(":", 1)[1]

        # 3) Prepare Score Objects for Template"""
content = content.replace(old_end_loop, new_end_loop)


# Fix 6: Inject basic_extras into cga_general
old_postal = """            "district": latest_cga.get("district"),
            "province": latest_cga.get("province"),
            "postal_code": latest_cga.get("postal_code")
        }"""
new_postal = """            "district": latest_cga.get("district"),
            "province": latest_cga.get("province"),
            "postal_code": latest_cga.get("postal_code")
        }
        
        # Inject parsed basic extras from local DB
        if "living_status" in basic_extras:
            cga_general["living_status"] = basic_extras["living_status"]
        if "height" in basic_extras:
            cga_general["height"] = basic_extras["height"]
        if "waist" in basic_extras:
            cga_general["waist"] = basic_extras["waist"]"""
content = content.replace(old_postal, new_postal)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
