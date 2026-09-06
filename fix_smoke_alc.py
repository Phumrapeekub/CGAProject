import os
import re

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix smoke
content = content.replace("{% if smoke=='yes' %}", "{% if smoke in ['yes', 'สูบ'] %}")
content = content.replace("{% if smoke=='no' %}", "{% if smoke in ['no', 'ไม่สูบ'] %}")
content = content.replace("{% if smoke=='quit' %}", "{% if smoke in ['quit', 'เลิกแล้ว'] %}")

# Fix alcohol
content = content.replace("{% if alc=='never' %}", "{% if alc in ['never', 'none', 'no', 'ไม่ดื่ม'] %}")
content = content.replace("{% if alc=='sometimes' %}", "{% if alc in ['sometimes', 'social', 'ดื่มบางครั้ง'] %}")
content = content.replace("{% if alc=='daily' %}", "{% if alc in ['daily', 'ดื่มทุกวัน'] %}")

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
