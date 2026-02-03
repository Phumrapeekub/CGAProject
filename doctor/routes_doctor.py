from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection  # หรือ from db import get_db_connection

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


@doctor_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, username, password_hash, role, is_active FROM users WHERE username=%s LIMIT 1",
            (username,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        role_db = (user.get("role") if user else "") or ""
        role_db = role_db.strip().lower()  # ✅ normalize

        ok = (
            user
            and user.get("is_active", 1) == 1
            and role_db == "doctor"  # ✅ ใช้ตัวเล็กเป็นมาตรฐาน
            and user.get("password_hash")
            and check_password_hash(user["password_hash"], password)
        )

        if not ok:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("doctor.login"))

        session.clear()
        session["logged_in"] = True
        session["user_id"] = user["id"]
        session["role"] = role_db  # ✅ เก็บเป็นตัวเล็ก
        return redirect(url_for("doctor.dashboard"))

    return render_template(
        "auth/login.html",
        role_label="แพทย์",
        page_title="Doctor Login",
        page_desc="กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ",
        post_url=url_for("doctor.login"),
        logo_path=url_for("static", filename="logo_phayao.png"),
    )


@doctor_bp.get("/dashboard")
def dashboard():
    if not session.get("logged_in") or session.get("role") != "doctor":  # ✅ ตัวเล็ก
        return redirect(url_for("doctor.login"))
    return "DOCTOR DASHBOARD OK"
