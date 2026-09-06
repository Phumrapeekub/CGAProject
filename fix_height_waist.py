import os
import re

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_str = """            "smoke": {'no':'ไม่สูบ','quit':'เลิกแล้ว','yes':'สูบ'}.get(data_map['smoke'], 'ไม่ระบุ'),
            "alcohol": {'none':'ไม่ดื่ม','no':'ไม่ดื่ม','social':'ดื่มบางครั้ง','daily':'ดื่มทุกวัน'}.get(data_map['alcohol'], 'ไม่ระบุ')
        }"""

new_str = """            "smoke": {'no':'ไม่สูบ','quit':'เลิกแล้ว','yes':'สูบ'}.get(data_map['smoke'], 'ไม่ระบุ'),
            "alcohol": {'none':'ไม่ดื่ม','no':'ไม่ดื่ม','social':'ดื่มบางครั้ง','daily':'ดื่มทุกวัน'}.get(data_map['alcohol'], 'ไม่ระบุ'),
            "height": data_map.get('height'),
            "waist": data_map.get('waist')
        }"""

content = content.replace(old_str, new_str)

with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
