import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                for row in ans_rows:
                    inst = str(row.get("instrument") or "").lower()
                    print(f"DEBUG LOOP: inst={inst}")
                    q_no = row.get("question_no")
                    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")"""

new_logic = """                for row in ans_rows:
                    inst = str(row.get("instrument") or "").lower()
                    q_no = row.get("question_no")
                    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")
                    txt = str(row.get("answer_text") or "").lower()"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
