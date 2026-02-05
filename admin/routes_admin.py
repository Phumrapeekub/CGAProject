from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection  # ถ้า db.py อยู่ root ให้เปลี่ยนเป็น: from db import get_db_connection

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/login", methods=["GET"])
def admin_login_redirect():
    return redirect(url_for("auth.login"))

@admin_bp.route("/login", methods=["GET", "POST"])
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

        ok = (
            user
            and user.get("is_active", 1) == 1
            and user.get("role") == "admin"
            and user.get("password_hash")
            and check_password_hash(user["password_hash"], password)
        )

        if not ok:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("admin.login"))

        session.clear()
        session["logged_in"] = True
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        return redirect(url_for("admin.dashboard"))

    return render_template(
        "auth/login.html",
        role_label="ผู้ดูแลระบบ",
        page_title="Admin Login",
        page_desc="กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ",
        post_url=url_for("admin.login"),
        logo_path=url_for("static", filename="logo_phayao.png"),
    )


@admin_bp.get("/dashboard")
def dashboard():
    if not session.get("logged_in") or session.get("role") != "admin":
        return redirect(url_for("admin.login"))
    return "ADMIN DASHBOARD OK"
