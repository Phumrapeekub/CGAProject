import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('q8_details[f"q8_{q_no}"] = val', 'q8_details[f"q{q_no}"] = val')

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
