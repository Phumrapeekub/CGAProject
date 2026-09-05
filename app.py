from __future__ import annotations
import os
from flask import Flask, redirect, jsonify
from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp
from supabase_utils import check_supabase_connection
from dotenv import load_dotenv
load_dotenv()


app = Flask(_name_)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_fallback")

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

@app.get("/check-supabase")
def supabase_status():
    result = check_supabase_connection()
    return jsonify(result)

if _name_ == "_main_":
    app.run(debug=True)