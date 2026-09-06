import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """        # Inject extras parsed from assessment_answers (local DB)
        if "living_status" in basic_extras:"""

new_logic = """        # Inject extras parsed from assessment_answers (local DB)
        print(f"DEBUG EXTRAS: {basic_extras}")
        if "living_status" in basic_extras:"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
