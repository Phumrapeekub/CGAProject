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

        conn = get_db_connection()
        if not conn:
            flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
            return redirect(url_for("auth.login"))

        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, username, password_hash, role, is_active, full_name
                FROM users
                WHERE username=%s
                LIMIT 1
                """,
                (username,),
            )
            user = cur.fetchone()
            cur.close()
        finally:
            conn.close()

        if not user:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("auth.login"))

        if not user.get("is_active", 1):
            flash("บัญชีถูกปิดการใช้งาน", "error")
            return redirect(url_for("auth.login"))

        if not check_password_hash(user["password_hash"], password):
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("auth.login"))

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user.get("role") or ""
        session["full_name"] = user.get("full_name") or ""

        role = (user.get("role") or "").lower()
        if role == "nurse":
            return redirect("/nurse/dashboard")
        if role == "doctor":
            return redirect("/doctor/dashboard")
        if role == "admin":
            return redirect("/admin/dashboard")

        flash("role ไม่ถูกต้อง", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
