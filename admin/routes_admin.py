from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from db.db import get_db_connection
from datetime import date

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


from datetime import date
from flask import render_template, request, redirect, url_for, flash, session

@admin_bp.route("/dashboard")
def dashboard():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    today = date.today()
    rk = request.args.get("range", "month")  # week | month | year

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
    "admin/dashboard.html",
    today=today,
    username=session.get("username"),
    stats=stats,
    latest_users=latest_users,
    range_key=request.args.get("range", "month"),

    weekly_labels=weekly_labels,
    weekly_values=weekly_values,
    type_labels=type_labels,
    type_values=type_values,
)


    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        # -------------------------
        # helpers
        # -------------------------
        def count_table(table: str) -> int:
            try:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                row = cur.fetchone() or {}
                return int(row.get("c") or 0)
            except Exception:
                return 0

        # -------------------------
        # stats (ให้ตรงกับการ์ดใน template)
        # -------------------------
        users_total = count_table("users")
        patients_total = count_table("patients")

        # ผู้ป่วยวันนี้ (นับจาก patients.created_at)
        today_patients = 0
        try:
            cur.execute(
                "SELECT COUNT(*) AS c FROM patients WHERE DATE(created_at) = CURDATE()"
            )
            today_patients = int((cur.fetchone() or {}).get("c") or 0)
        except Exception:
            today_patients = 0

        # นัดหมายวันนี้ (นับจาก appointments.appt_datetime)
        appointments_today = 0
        try:
            cur.execute(
                "SELECT COUNT(*) AS c FROM appointments WHERE DATE(appt_datetime) = CURDATE()"
            )
            appointments_today = int((cur.fetchone() or {}).get("c") or 0)
        except Exception:
            appointments_today = 0

        # การประเมินวันนี้ (พยายามนับจาก assessment_sessions.assessed_at ถ้ามี)
        assessments_today = 0
        try:
            cur.execute(
                "SELECT COUNT(*) AS c FROM assessment_sessions WHERE DATE(assessed_at) = CURDATE()"
            )
            assessments_today = int((cur.fetchone() or {}).get("c") or 0)
        except Exception:
            assessments_today = 0

        stats = {
            "users": users_total,
            "patients": patients_total,
            "today_patients": today_patients,
            "appointments_today": appointments_today,
            "assessments_today": assessments_today,
        }

        # -------------------------
        # latest users
        # -------------------------
        cur.execute(
            """
            SELECT u.username, r.name AS role, u.created_at
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            ORDER BY u.created_at DESC
            LIMIT 5
            """
        )
        latest_users = cur.fetchall() or []

        # -------------------------
        # LINE CHART: patients ตามช่วงเวลา (ใช้ patients.created_at)
        #   week  = 7 วันล่าสุด (รายวัน)
        #   month = เดือนนี้ (รายสัปดาห์)
        #   year  = 12 เดือนล่าสุด (รายเดือน)
        # -------------------------
        weekly_labels, weekly_values = [], []

        if rk == "week":
            cur.execute(
                """
                SELECT DATE(created_at) AS label, COUNT(*) AS value
                FROM patients
                WHERE created_at >= CURDATE() - INTERVAL 6 DAY
                GROUP BY DATE(created_at)
                ORDER BY label
                """
            )
            rows = cur.fetchall() or []
            weekly_labels = [str(r["label"]) for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        elif rk == "year":
            cur.execute(
                """
                SELECT DATE_FORMAT(created_at, '%Y-%m') AS label, COUNT(*) AS value
                FROM patients
                WHERE created_at >= (CURDATE() - INTERVAL 11 MONTH)
                GROUP BY DATE_FORMAT(created_at, '%Y-%m')
                ORDER BY label
                """
            )
            rows = cur.fetchall() or []
            weekly_labels = [r["label"] for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        else:  # month (default)
            cur.execute(
                """
                SELECT CONCAT('สัปดาห์ ', WEEK(created_at, 1) - WEEK(DATE_SUB(created_at, INTERVAL DAYOFMONTH(created_at)-1 DAY), 1) + 1) AS label,
                       COUNT(*) AS value
                FROM patients
                WHERE MONTH(created_at) = MONTH(CURDATE())
                  AND YEAR(created_at) = YEAR(CURDATE())
                GROUP BY label
                ORDER BY MIN(created_at)
                """
            )
            rows = cur.fetchall() or []
            weekly_labels = [r["label"] for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        # กันกราฟพัง ถ้าไม่มีข้อมูลเลย
        if not weekly_labels:
            weekly_labels = ["สัปดาห์ 1", "สัปดาห์ 2", "สัปดาห์ 3", "สัปดาห์ 4"]
            weekly_values = [0, 0, 0, 0]

        # -------------------------
        # BAR CHART: "ประเภทบริการ" จาก appointments.appt_type
        #   แทนการแยกตามแผนก (เพราะของคุณเจาะจงอายุรกรรม)
        # -------------------------
        # filter ตามช่วงเวลาโดยอิง appt_datetime
        if rk == "week":
            where_sql = "WHERE appt_datetime >= NOW() - INTERVAL 6 DAY"
        elif rk == "year":
            where_sql = "WHERE appt_datetime >= NOW() - INTERVAL 11 MONTH"
        else:
            where_sql = "WHERE MONTH(appt_datetime) = MONTH(CURDATE()) AND YEAR(appt_datetime) = YEAR(CURDATE())"

        cur.execute(
            f"""
            SELECT appt_type AS label, COUNT(*) AS value
            FROM appointments
            {where_sql}
            GROUP BY appt_type
            ORDER BY value DESC
            """
        )
        type_rows = cur.fetchall() or []

        # map ให้ชื่ออ่านง่าย
        nice_name = {
            "followup": "ติดตามอาการ",
            "cga": "ประเมิน CGA",
            "other": "อื่นๆ",
        }

        type_labels = []
        type_values = []
        for r in type_rows:
            raw = (r.get("label") or "other")
            type_labels.append(nice_name.get(raw, f"อื่น ๆ ({raw})"))
            type_values.append(int(r.get("value") or 0))

        if not type_labels:
            type_labels = ["ติดตามอาการ", "ประเมิน CGA", "อื่นๆ"]
            type_values = [0, 0, 0]

        return render_template(
            "admin/dashboard.html",
            today=today,
            username=session.get("username"),
            stats=stats,
            latest_users=latest_users,
            range_key=rk,
            weekly_labels=weekly_labels,
            weekly_values=weekly_values,
            type_labels=type_labels,
            type_values=type_values,
        )

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@admin_bp.get("/patients")
def patients_list():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", "1")
    try:
        page = max(int(page), 1)
    except Exception:
        page = 1

    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
            "admin/patients.html",
            username=session.get("username"),
            q=q,
            patients=[],
            page=page,
            total_pages=1,
            total_rows=0,
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        where = ""
        params = []
        if q:
            where = "WHERE hn LIKE %s OR full_name LIKE %s"
            like = f"%{q}%"
            params.extend([like, like])

        # total rows
        cur.execute(f"SELECT COUNT(*) AS c FROM patients {where}", params)
        total_rows = int((cur.fetchone() or {}).get("c", 0) or 0)
        total_pages = max((total_rows + per_page - 1) // per_page, 1)

        # rows
        cur.execute(
            f"""
            SELECT id, hn, full_name, gender, birth_date, phone, address, created_at
            FROM patients
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [per_page, offset],
        )
        patients = cur.fetchall() or []

        return render_template(
            "admin/patients.html",
            username=session.get("username"),
            q=q,
            patients=patients,
            page=page,
            total_pages=total_pages,
            total_rows=total_rows,
        )

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
