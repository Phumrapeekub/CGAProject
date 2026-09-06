import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_cga_general = """        # General info: prefer latest_cga, then latest_c
        cga_general = {
            "caregiver_name": latest_cga.get("caregiver_name") or latest_c.get("caregiver_name") or "-", 
            "caregiver_phone": latest_cga.get("phone") or latest_c.get("caregiver_phone") or "-",
            "caregiver_relation": latest_c.get("caregiver_relation") or "-",
            "disease": latest_cga.get("comorbidity_detail") or latest_c.get("note_from_nurse"),"""

new_cga_general = """        # General info: prefer latest_cga, then latest_c
        cga_general = {
            "caregiver_name": latest_cga.get("caregiver_name") or latest_c.get("caregiver_name") or "-", 
            "caregiver_phone": latest_cga.get("emergency_phone") or latest_c.get("caregiver_phone") or "-",
            "living_status": latest_cga.get("living_status") or "-",
            "caregiver_relation": latest_c.get("caregiver_relation") or "-",
            "disease": latest_cga.get("comorbidity_detail") or latest_c.get("note_from_nurse"),"""

content = content.replace(old_cga_general, new_cga_general)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
