
with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
for i, line in enumerate(lines):
    if "/assess/step1/save/" in line:
        start_idx = i
        break

if start_idx != -1:
    lines = lines[:start_idx]

with open('tail_nurse.py', 'r', encoding='utf-8') as f:
    tail = f.read()

with open('nurse/routes_nurse.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
    f.write('
' + tail)
