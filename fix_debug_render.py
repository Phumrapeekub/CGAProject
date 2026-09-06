import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """        return render_template(
            "doctor/medical_patients_detail.html","""

new_logic = """        print(f"DEBUG RENDER: living_status={cga_general.get('living_status')}")
        return render_template(
            "doctor/medical_patients_detail.html","""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
