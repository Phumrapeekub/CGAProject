from __future__ import annotations
from flask import Flask, redirect
from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.secret_key = "dev_secret_key"

# ตั้งค่าให้ Session ทำงานได้เมื่อฝังเว็บใน iframe ของ Hugging Face
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None',
)

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(nurse_bp)

@app.get("/")
def root():
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)
