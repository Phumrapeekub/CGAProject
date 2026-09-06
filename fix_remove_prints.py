import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'print\(f"DEBUG BASIC VAL: \{val\}"\)\s*', '', content)
content = re.sub(r'print\(f"DEBUG LOOP: inst=\{inst\}"\)\s*', '', content)
content = re.sub(r'print\(f"DEBUG: Mapped MMSE answer \{txt\}=\{row.get\(\'score\'\)\}"\)\s*', '', content)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
