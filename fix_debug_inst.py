import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                for row in ans_rows:
                    inst = str(row.get("instrument") or "").lower()"""

new_logic = """                for row in ans_rows:
                    inst = str(row.get("instrument") or "").lower()
                    print(f"DEBUG LOOP: inst={inst}")"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
