import os
import re

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("p.get('name')", "(p.get('full_name') or p.get('name'))")
content = content.replace("p.name if p.name is defined", "(p.full_name if p.full_name is defined else (p.name if p.name is defined else ''))")

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
