import os
import re

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'\{% set p_name = .*? %\}', "{% set p_name = p.get('full_name') or p.get('name') or '' %}", content, count=1)

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
