import os

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("sex_map = {'male': 'ชาย', 'female': 'หญิง'}", "")
content = content.replace("sex_map.get(p_latest['gender'], p_latest['gender'])", "p_latest['gender']")
content = content.replace("sex_map.get(p_raw['gender'], p_raw['gender'])", "p_raw['gender']")
content = content.replace("sex_map.get(p_row['gender'], p_row['gender'])", "p_row['gender']")

with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
