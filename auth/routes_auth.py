from __future__ import annotations
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection
from mysql.connector import Error as MySQLdbError # Import MySQL Error

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน", "error")
            return redirect(url_for("auth.login"))

        conn = None
        cur = None
        try:
            conn = get_db_connection()
            if not conn:
                flash("ไม่สามารถเชื่อมต่อฐานข้อมูลได้", "error")
                return redirect(url_for("auth.login"))
            
            cur = conn.cursor(dictionary=True)
            
            # Query user using MySQL
            cur.execute(
                "SELECT id, username, password_hash, is_active, full_name, role FROM users WHERE username = %s LIMIT 1",
                (username,)
            )
            user = cur.fetchone()

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

            # Log login to audit_logs
            try:
                ip_addr = request.remote_addr
                user_agent = request.headers.get("User-Agent")
                cur.execute("""
                    INSERT INTO audit_logs (actor_user_id, actor_role, action, entity_type, ip_address, user_agent)
                    VALUES (%s, %s, 'login', 'auth', %s, %s)
                """, (user["id"], user["role"], ip_addr, user_agent))
                conn.commit()
            except Exception as ex:
                print(f"Audit Log Error: {ex}") # Don't block login if logging fails

            # Redirect based on role
            role = session["role"]
            if role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif role == "doctor":
                return redirect(url_for("doctor.dashboard"))
            elif role == "nurse":
                return redirect(url_for("nurse.dashboard"))
            else:
                flash("บทบาทไม่ถูกต้องหรือไม่มีสิทธิ์เข้าถึง", "error")
                return redirect(url_for("auth.login"))

        except MySQLdbError as e:
            print(f"Login DB Error: {e}")
            flash(f"เกิดข้อผิดพลาดฐานข้อมูล: {e}", "error")
            return redirect(url_for("auth.login"))
        except Exception as e:
            print(f"Login Error: {e}")
            flash(f"เกิดข้อผิดพลาดในการเข้าสู่ระบบ: {e}", "error")
            return redirect(url_for("auth.login"))
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    return render_template(
        "auth/login.html", 
        post_url=url_for("auth.login"),
        logo_path=url_for('static', filename='logo.png'),
        page_title="CGA System Login",
        page_desc="ระบบประเมินสุขภาพผู้สูงอายุ โรงพยาบาลพะเยา"
    )