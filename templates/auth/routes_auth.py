from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash

from db.db import get_db_connection  # ถ้า db อยู่ root ชื่อ db.py ให้เปลี่ยนเป็น: from db import get_db_connection

auth_bp = Blueprint("auth", __name__)


def _login_for_role(role: str, title: str):
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

        ok = (
            user
            and user.get("is_active", 1) == 1
            and user.get("role") == role
            and user.get("password_hash")
            and check_password_hash(user["password_hash"], password)
        )

        if not ok:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(request.path)

        # ✅ ผ่าน
        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["logged_in"] = True

        # redirect ตาม role
        if role == "admin":
            return redirect(url_for("admin.dashboard"))
        if role == "doctor":
            return redirect(url_for("doctor.dashboard"))
        return redirect(url_for("nurse.dashboard"))

    # GET => render UI เดียว
    role_label_map = {"admin": "ผู้ดูแลระบบ", "doctor": "แพทย์", "nurse": "พยาบาล"}
    return render_template(
        "auth/login.html",
        role_label=role_label_map.get(role, role),
        page_title=title,
        page_desc="กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ",
        post_url=request.path,  # โพสต์กลับ URL เดิม
        logo_path=url_for("static", filename="logo_phayao.png"),
    )


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    return _login_for_role("admin", "Admin Login")


@auth_bp.route("/doctor/login", methods=["GET", "POST"])
def doctor_login():
    return _login_for_role("doctor", "Doctor Login")


@auth_bp.route("/nurse/login", methods=["GET", "POST"])
def nurse_login():
    return _login_for_role("nurse", "Nurse Login")


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.admin_login"))
