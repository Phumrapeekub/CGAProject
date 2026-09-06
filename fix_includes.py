import os

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Fix include paths
content = re.sub(r'\{% include "assess/([^"]+)" %\}', r'{% include "doctor/assess/\1" %}', content)

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
