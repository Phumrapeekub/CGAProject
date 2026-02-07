from __future__ import annotations
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน", "error")
            return redirect(url_for("auth.login"))

        supabase = get_db_connection()
        if not supabase:
            flash("เชื่อมต่อ Supabase API ไม่สำเร็จ", "error")
            return redirect(url_for("auth.login"))

        try:
            # Query user using Supabase SDK
            response = supabase.table("users").select(
                "id, username, password_hash, is_active, full_name, role"
            ).eq("username", username).limit(1).execute()
            
            user = response.data[0] if response.data else None

            if not user:
                flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
                return redirect(url_for("auth.login"))

            # Check password
            if not check_password_hash(user["password_hash"], password):
                flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
                return redirect(url_for("auth.login"))

            if not user.get("is_active", True):
                flash("บัญชีนี้ถูกระงับการใช้งาน", "error")
                return redirect(url_for("auth.login"))

            # Setup session
            session.clear()
            session["logged_in"] = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"].lower() if user["role"] else ""

            # Redirect based on role
            role = session["role"]
            if role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif role == "doctor":
                return redirect(url_for("doctor.dashboard"))
            elif role == "nurse":
                return redirect(url_for("nurse.dashboard"))
            else:
                return redirect(url_for("auth.login"))

        except Exception as e:
            print(f"Login Error: {e}")
            flash("เกิดข้อผิดพลาดในการเข้าสู่ระบบ", "error")
            return redirect(url_for("auth.login"))

    return render_template("auth/login.html", post_url=url_for("auth.login"))

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))