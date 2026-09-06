import os

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("url_for('doctor_dashboard')", "url_for('doctor.dashboard')")

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
