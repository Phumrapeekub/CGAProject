import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                elif inst == "basic":
                    if txt and txt.startswith("live:"):
                        l = txt.split(":", 1)[1]
                        basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                    elif txt and txt.startswith("height:"):
                        basic_extras["height"] = txt.split(":", 1)[1]
                    elif txt and txt.startswith("waist:"):
                        basic_extras["waist"] = txt.split(":", 1)[1]"""

new_logic = """                elif inst == "basic":
                    if val and isinstance(val, str):
                        if val.startswith("live:"):
                            l = val.split(":", 1)[1]
                            basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                        elif val.startswith("height:"):
                            basic_extras["height"] = val.split(":", 1)[1]
                        elif val.startswith("waist:"):
                            basic_extras["waist"] = val.split(":", 1)[1]"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
