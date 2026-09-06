import os

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """        if q8_val == 0:
            # 2. Fallback:  assessment_answers ( followup  3)
            cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s AND (instrument='depression8Q' OR instrument='depression8Q_sub')", (data.get('session_id'),))
            ans8q = cur.fetchall()
            q8_weights = {1:1, 2:2, 3:4, 4:6, 5:8, 6:9, 7:9, 8:4}
            q3_v = 'no'; q3_s = 'no'
            temp_score = 0
            for r in ans8q:
                if r['instrument'] == 'depression8Q':
                    try:
                        q_idx = int(r['question_no'])
                        q8_details[str(q_idx)] = 'มี' if r['answer_text'] == 'yes' else 'ไม่มี'
                        if r['answer_text'] == 'yes':
                            temp_score += q8_weights.get(q_idx, 0)
                            if q_idx == 3: q3_v = 'yes'
                    except: pass
                elif r['instrument'] == 'depression8Q_sub':
                    q3_s = r['answer_text']
            
            if q3_v == 'yes' and q3_s == 'yes':
                temp_score += 10
            q8_val = temp_score"""

new_logic = """        # ALWAYS fetch individual answers for the UI list
        cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s AND (instrument='depression8Q' OR instrument='depression8Q_sub')", (data.get('session_id'),))
        ans8q = cur.fetchall()
        q8_weights = {1:1, 2:2, 3:4, 4:6, 5:8, 6:9, 7:9, 8:4}
        q3_v = 'no'; q3_s = 'no'
        temp_score = 0
        for r in ans8q:
            if r['instrument'] == 'depression8Q':
                try:
                    q_idx = int(r['question_no'])
                    q8_details[str(q_idx)] = 'มี' if r['answer_text'] == 'yes' else 'ไม่มี'
                    if r['answer_text'] == 'yes':
                        temp_score += q8_weights.get(q_idx, 0)
                        if q_idx == 3: q3_v = 'yes'
                except: pass
            elif r['instrument'] == 'depression8Q_sub':
                q3_s = r['answer_text']
        
        if q3_v == 'yes' and q3_s == 'yes':
            temp_score += 10
            
        if q8_val == 0:
            q8_val = temp_score"""

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print("SUCCESS: 8Q details logic fixed.")
else:
    print("FAILED: Target block not found. Trying flexible replacement.")
    # In case there are encoding issues with the Thai text 'มี' / 'ไม่มี'
