import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Initialize temp vars BEFORE loop (near mmse_details = {})
old_details = """        mmse_details = {}
        tgds_details = {}
        q8_details = {}"""
new_details = """        mmse_details = {}
        tgds_details = {}
        q8_details = {}
        twoq_details = {}
        basic_extras = {}"""
content = content.replace(old_details, new_details)

# 2. Store in temp vars DURING loop
old_logic = """                elif inst == "2q":
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

new_logic = """                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"
                elif inst == "basic":
                    if txt and txt.startswith("live:"):
                        l = txt.split(":", 1)[1]
                        basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                    elif txt and txt.startswith("height:"):
                        basic_extras["height"] = txt.split(":", 1)[1]
                    elif txt and txt.startswith("waist:"):
                        basic_extras["waist"] = txt.split(":", 1)[1]

        # 3) Prepare Score Objects for Template"""
content = content.replace(old_logic, new_logic)

# 3. Inject into cga_general AFTER initialization
old_cga = """            "district": latest_cga.get("district"),
            "province": latest_cga.get("province"),
            "postal_code": latest_cga.get("postal_code")
        }"""
new_cga = """            "district": latest_cga.get("district"),
            "province": latest_cga.get("province"),
            "postal_code": latest_cga.get("postal_code")
        }
        
        # Inject extras parsed from assessment_answers (local DB)
        if "living_status" in basic_extras:
            cga_general["living_status"] = basic_extras["living_status"]
        if "height" in basic_extras:
            cga_general["height"] = basic_extras["height"]
        if "waist" in basic_extras:
            cga_general["waist"] = basic_extras["waist"]"""
content = content.replace(old_cga, new_cga)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
