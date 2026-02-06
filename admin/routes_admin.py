
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
            stats={
                "users": 0,
                "patients": 0,
                "today_patients": 0,
                "appointments_today": 0,
                "assessments_today": 0,
            },
            latest_users=[],
            range_key=rk,
            weekly_labels=["สัปดาห์ 1", "สัปดาห์ 2", "สัปดาห์ 3", "สัปดาห์ 4"],
            weekly_values=[0, 0, 0, 0],
            type_labels=["ติดตามอาการ", "ประเมิน CGA", "อื่นๆ"],
            type_values=[0, 0, 0],
            active_page="dashboard",   # ✅ เพิ่มตรงนี้
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        def count_table(table: str) -> int:
            try:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                row = cur.fetchone() or {}
                return int(row.get("c") or 0)
            except Exception:
                return 0

        users_total = count_table("users")
        patients_total = count_table("patients")

        today_patients = 0
        try:
            cur.execute("SELECT COUNT(*) AS c FROM patients WHERE DATE(created_at) = CURDATE()")
            today_patients = int((cur.fetchone() or {}).get("c") or 0)
        except Exception:
            today_patients = 0

        appointments_today = 0
        try:
            cur.execute("SELECT COUNT(*) AS c FROM appointments WHERE DATE(appt_datetime) = CURDATE()")
            appointments_today = int((cur.fetchone() or {}).get("c") or 0)
        except Exception:
            appointments_today = 0

        assessments_today = 0
        try:
            cur.execute("SELECT COUNT(*) AS c FROM assessment_sessions WHERE DATE(assessed_at) = CURDATE()")
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

        cur.execute("""
            SELECT u.username, r.name AS role, u.created_at
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            ORDER BY u.created_at DESC
            LIMIT 5
        """)
        latest_users = cur.fetchall() or []

        weekly_labels, weekly_values = [], []

        if rk == "week":
            cur.execute("""
                SELECT DATE(created_at) AS label, COUNT(*) AS value
                FROM patients
                WHERE created_at >= CURDATE() - INTERVAL 6 DAY
                GROUP BY DATE(created_at)
                ORDER BY label
            """)
            rows = cur.fetchall() or []
            weekly_labels = [str(r["label"]) for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        elif rk == "year":
            cur.execute("""
                SELECT DATE_FORMAT(created_at, '%Y-%m') AS label, COUNT(*) AS value
                FROM patients
                WHERE created_at >= (CURDATE() - INTERVAL 11 MONTH)
                GROUP BY DATE_FORMAT(created_at, '%Y-%m')
                ORDER BY label
            """)
            rows = cur.fetchall() or []
            weekly_labels = [r["label"] for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        else:
            cur.execute("""
                SELECT CONCAT('สัปดาห์ ', WEEK(created_at, 1) - WEEK(DATE_SUB(created_at, INTERVAL DAYOFMONTH(created_at)-1 DAY), 1) + 1) AS label,
                       COUNT(*) AS value
                FROM patients
                WHERE MONTH(created_at) = MONTH(CURDATE())
                  AND YEAR(created_at) = YEAR(CURDATE())
                GROUP BY label
                ORDER BY MIN(created_at)
            """)
            rows = cur.fetchall() or []
            weekly_labels = [r["label"] for r in rows]
            weekly_values = [int(r["value"]) for r in rows]

        if not weekly_labels:
            weekly_labels = ["สัปดาห์ 1", "สัปดาห์ 2", "สัปดาห์ 3", "สัปดาห์ 4"]
            weekly_values = [0, 0, 0, 0]

        if rk == "week":
            where_sql = "WHERE appt_datetime >= NOW() - INTERVAL 6 DAY"
        elif rk == "year":
            where_sql = "WHERE appt_datetime >= NOW() - INTERVAL 11 MONTH"
        else:
            where_sql = "WHERE MONTH(appt_datetime) = MONTH(CURDATE()) AND YEAR(appt_datetime) = YEAR(CURDATE())"

        cur.execute(f"""
            SELECT appt_type AS label, COUNT(*) AS value
            FROM appointments
            {where_sql}
            GROUP BY appt_type
            ORDER BY value DESC
        """)
        type_rows = cur.fetchall() or []

        nice_name = {"followup": "ติดตามอาการ", "cga": "ประเมิน CGA", "other": "อื่นๆ"}

        type_labels, type_values = [], []
        for r in type_rows:
            raw = (r.get("label") or "other")
            type_labels.append(nice_name.get(raw, f"อื่น ๆ ({raw})"))
            type_values.append(int(r.get("value") or 0))

        if not type_labels:
            type_labels = ["ติดตามอาการ", "ประเมิน CGA", "อื่นๆ"]
            type_values = [0, 0, 0]
            # ✅ ลบ active_page="dashboard", ที่เคยหลุดอยู่ตรงนี้ออก

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
            active_page="dashboard",
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
            active_page="patients",
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
            active_page="patients"
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

@admin_bp.get("/appointments")
def appointments_list():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    date_mode = request.args.get("date")  # today | None

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
            "admin/appointments.html",
            username=session.get("username"),
            appointments=[],
            date_mode=date_mode,
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT 
                a.id,
                a.patient_id,
                p.hn,
                p.full_name,
                a.appt_datetime,
                a.appt_type,
                a.note
            FROM appointments a
            LEFT JOIN patients p ON p.id = a.patient_id
        """

        if date_mode == "today":
            sql += " WHERE DATE(a.appt_datetime) = CURDATE()"

        sql += " ORDER BY a.appt_datetime DESC LIMIT 200"

        cur.execute(sql)
        appointments = cur.fetchall() or []

        return render_template(
            "admin/appointments.html",
            username=session.get("username"),
            appointments=appointments,
            date_mode=date_mode,
            active_page="appointments"
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


@admin_bp.get("/assessments")
def assessments_list():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    date_mode = request.args.get("date")  # today | None

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
            "admin/assessments.html",
            username=session.get("username"),
            assessments=[],
            date_mode=date_mode,
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT 
                s.id,
                s.patient_id,
                p.hn,
                p.full_name,
                s.assessed_at,
                s.created_at
            FROM assessment_sessions s
            LEFT JOIN patients p ON p.id = s.patient_id
        """

        if date_mode == "today":
            sql += " WHERE DATE(s.assessed_at) = CURDATE()"

        sql += " ORDER BY s.assessed_at DESC LIMIT 200"

        cur.execute(sql)
        assessments = cur.fetchall() or []

        return render_template(
            "admin/assessments.html",
            username=session.get("username"),
            assessments=assessments,
            date_mode=date_mode,
            active_page="assessments"
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


@admin_bp.get("/doctors")
def doctors_list():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template(
            "admin/doctors.html",
            doctors=[],
            username=session.get("username"),
            active_page="doctors",
        )

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        # ดึงรายชื่อแพทย์ + นับเวรเดือนนี้
        cur.execute(
            """
            SELECT 
                u.id,
                u.full_name,
                u.username,
                u.is_active,
                COUNT(d.id) AS duty_count
            FROM users u
            LEFT JOIN doctor_duties d 
                ON d.doctor_id = u.id
                AND MONTH(d.duty_date) = MONTH(CURDATE())
                AND YEAR(d.duty_date) = YEAR(CURDATE())
            WHERE u.role = 'doctor'
            GROUP BY u.id
            ORDER BY u.full_name
            """
        )
        doctors = cur.fetchall() or []

        return render_template(
            "admin/doctors.html",
            doctors=doctors,
            username=session.get("username"),
            active_page="doctors",
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


@admin_bp.get("/doctors/<int:doctor_id>/duties")
def doctor_duties(doctor_id: int):
    if not _require_admin():
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("admin.doctors_list"))

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        # ข้อมูลแพทย์
        cur.execute(
            """
            SELECT id, full_name, username
            FROM users
            WHERE id = %s AND role = 'doctor'
            """,
            (doctor_id,),
        )
        doctor = cur.fetchone()

        if not doctor:
            flash("ไม่พบแพทย์", "error")
            return redirect(url_for("admin.doctors_list"))

        # เวรแพทย์
        cur.execute(
            """
            SELECT duty_date, shift_type, start_time, end_time, location, note
            FROM doctor_duties
            WHERE doctor_id = %s
            ORDER BY duty_date DESC
            """,
            (doctor_id,),
        )
        duties = cur.fetchall() or []

        return render_template(
            "admin/doctor_duties.html",
            doctor=doctor,
            duties=duties,
            username=session.get("username"),
            active_page="doctors",
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


@admin_bp.get("/nurses")
def nurses_list():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    # เอาไว้กันหน้าแตกก่อน (ยังไม่เชื่อม db ก็ได้)
    return render_template(
        "admin/nurses.html",
        username=session.get("username"),
        nurses=[],
        active_page="nurses",
    )




@admin_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
