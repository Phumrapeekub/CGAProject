import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"

        # 3) Prepare Score Objects for Template"""

new_logic = """                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"
                elif inst == "basic":
                    if txt and txt.startswith("live:"):
                        l = txt.split(":", 1)[1]
                        cga_general["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                    elif txt and txt.startswith("height:"):
                        cga_general["height"] = txt.split(":", 1)[1]
                    elif txt and txt.startswith("waist:"):
                        cga_general["waist"] = txt.split(":", 1)[1]

        # 3) Prepare Score Objects for Template"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
