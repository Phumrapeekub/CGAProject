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

        conn = get_db_connection()
        if not conn:
            flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
            return redirect(url_for("auth.login"))

        cur = None
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.password_hash,
                    u.is_active,
                    u.full_name,
                    COALESCE(r.code, u.role) AS role_code
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                WHERE u.username = %s
                LIMIT 1
                """,
                (username,),
            )
            user = cur.fetchone()
        finally:
            try:
                if cur:
                    cur.close()
            except Exception:
                pass
            conn.close()

        if not user:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("auth.login"))

        if int(user.get("is_active", 1)) != 1:
            flash("บัญชีถูกปิดการใช้งาน", "error")
            return redirect(url_for("auth.login"))

        pwd_hash = user.get("password_hash") or ""
        if not pwd_hash or not check_password_hash(pwd_hash, password):
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
            return redirect(url_for("auth.login"))

        role_norm = (user.get("role_code") or "").strip().lower()

        # ✅ session มาตรฐาน (ใช้ชุดเดียวทั้งระบบ)
        session.clear()
        session["logged_in"] = True
        session["user_id"] = int(user["id"])
        session["username"] = (user.get("username") or "").strip()
        session["full_name"] = (user.get("full_name") or "").strip()
        session["role"] = role_norm

        print("LOGIN:", session["username"], "ROLE =", session["role"])

        # redirect ตาม role
        if role_norm == "nurse":
            return redirect("/nurse/dashboard")
        if role_norm == "doctor":
            return redirect("/doctor/dashboard")
        if role_norm == "admin":
            return redirect("/admin/dashboard")

        flash(f"role ไม่ถูกต้อง: {role_norm}", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
