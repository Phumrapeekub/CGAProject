import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = -1
for i in range(1250, 1270):
    if 'elif row.get("answer_text") == "can_control":' in lines[i]:
        insert_idx = i + 2
        break

if insert_idx != -1:
    lines.insert(insert_idx, '                    elif inst == "basic":\n')
    lines.insert(insert_idx + 1, '                        if val and isinstance(val, str):\n')
    lines.insert(insert_idx + 2, '                            if val.startswith("live:"):\n')
    lines.insert(insert_idx + 3, '                                l = val.split(":", 1)[1]\n')
    lines.insert(insert_idx + 4, '                                basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l\n')
    lines.insert(insert_idx + 5, '                            elif val.startswith("height:"):\n')
    lines.insert(insert_idx + 6, '                                basic_extras["height"] = val.split(":", 1)[1]\n')
    lines.insert(insert_idx + 7, '                            elif val.startswith("waist:"):\n')
    lines.insert(insert_idx + 8, '                                basic_extras["waist"] = val.split(":", 1)[1]\n')

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.writelines(lines)
