from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, flash, session
from db.db import get_db_connection

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    return (
        session.get("logged_in")
        and session.get("role") == "admin"
        and session.get("user_id")
    )


@admin_bp.get("/")
def index():
    if _require_admin():
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("auth.login"))


@admin_bp.get("/dashboard")
def dashboard():
    if not _require_admin():
        flash("ไม่มีสิทธิ์เข้าหน้านี้", "error")
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
            "admin/dashboard.html",
            username=session.get("username"),
            stats={"users": 0, "patients": 0, "encounters": 0},
            latest_users=[],
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        def count(table: str) -> int:
            try:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                return int((cur.fetchone() or {}).get("c", 0) or 0)
            except Exception:
                return 0

        stats = {
            "users": count("users"),
            "patients": count("patients"),
            "encounters": count("encounters"),
        }

        # ผู้ใช้ล่าสุด
        cur.execute(
            """
            SELECT u.username, r.code AS role
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            ORDER BY u.id DESC
            LIMIT 5
            """
        )
        latest_users = cur.fetchall() or []

        return render_template(
            "admin/dashboard.html",
            username=session.get("username"),
            stats=stats,
            latest_users=latest_users,
        )

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        conn.close()
