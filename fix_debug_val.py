import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                elif inst == "basic":
                    if val and isinstance(val, str):
                        if val.startswith("live:"):"""

new_logic = """                elif inst == "basic":
                    print(f"DEBUG BASIC: {val}")
                    if val and isinstance(val, str):
                        if val.startswith("live:"):"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
