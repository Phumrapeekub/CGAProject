from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash

from db.db import get_db_connection  # ถ้า db อยู่ root เป็น db.py ให้เปลี่ยนเป็น: from db import get_db_connection

auth_bp = Blueprint("auth", __name__)


def _login_for_role(role: str, page_title: str, post_endpoint: str):
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
            return redirect(url_for(post_endpoint))

        # ✅ ผ่าน
        session.clear()
        session["logged_in"] = True
        session["user_id"] = user["id"]
        session["role"] = user["role"]

        if role == "admin":
            return redirect(url_for("admin.dashboard"))
        if role == "doctor":
            return redirect(url_for("doctor.dashboard"))
        return redirect(url_for("nurse.dashboard"))

    role_label_map = {"admin": "ผู้ดูแลระบบ", "doctor": "แพทย์", "nurse": "พยาบาล"}
    return render_template(
        "auth/login.html",
        role_label=role_label_map.get(role, role),
        page_title=page_title,
        page_desc="กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ",
        post_url=url_for(post_endpoint),
        logo_path=url_for("static", filename="logo_phayao.png"),
    )


# ✅ ค่าเริ่มต้นเดิม /login (ให้ redirect ไป admin login)
@auth_bp.get("/login")
def login_get():
    return redirect(url_for("auth.admin_login_get"))


@auth_bp.post("/login")
def login_post():
    return redirect(url_for("auth.admin_login_get"))


# ✅ Admin
@auth_bp.get("/admin/login")
def admin_login_get():
    return _login_for_role("admin", "Admin Login", "auth.admin_login_post")


@auth_bp.post("/admin/login")
def admin_login_post():
    return _login_for_role("admin", "Admin Login", "auth.admin_login_post")


# ✅ Doctor
@auth_bp.get("/doctor/login")
def doctor_login_get():
    return _login_for_role("doctor", "Doctor Login", "auth.doctor_login_post")


@auth_bp.post("/doctor/login")
def doctor_login_post():
    return _login_for_role("doctor", "Doctor Login", "auth.doctor_login_post")


# ✅ Nurse
@auth_bp.get("/nurse/login")
def nurse_login_get():
    return _login_for_role("nurse", "Nurse Login", "auth.nurse_login_post")


@auth_bp.post("/nurse/login")
def nurse_login_post():
    return _login_for_role("nurse", "Nurse Login", "auth.nurse_login_post")


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.admin_login_get"))
