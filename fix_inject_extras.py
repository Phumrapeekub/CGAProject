import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """        return render_template(
            "doctor/medical_patients_detail.html","""

new_logic = """        if "living_status" in basic_extras:
            cga_general["living_status"] = basic_extras["living_status"]
        if "height" in basic_extras:
            cga_general["height"] = basic_extras["height"]
        if "waist" in basic_extras:
            cga_general["waist"] = basic_extras["waist"]

        return render_template(
            "doctor/medical_patients_detail.html","""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
