from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection  # หรือ from db import get_db_connection
from datetime import date
from datetime import datetime, date, timedelta
from flask import jsonify

def _guard_doctor() -> bool:
    return bool(session.get("logged_in")) and session.get("role") == "doctor"


def _thai_months_full():
    return [
        "มกราคม",
        "กุมภาพันธ์",
        "มีนาคม",
        "เมษายน",
        "พฤษภาคม",
        "มิถุนายน",
        "กรกฎาคม",
        "สิงหาคม",
        "กันยายน",
        "ตุลาคม",
        "พฤศจิกายน",
        "ธันวาคม",
    ]


def _thai_months_short():
    return ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def format_thai_short_with_year(d: date) -> str:
    # เวอร์ชันกันพัง (ง่ายๆ)
    m = _thai_months_full()[d.month - 1]
    y = d.year + 543
    return f"{d.day} {m[:3]} {y}"


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
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor.login"))

    cur = conn.cursor(dictionary=True)

    def count_sql(sql: str, params=(), key: str = "n") -> int:
        cur.execute(sql, params)
        row = cur.fetchone() or {}
        return int((row.get(key) or 0))

    try:
        # --------------------------
        # KPI: patients
        # --------------------------
        total_patients = count_sql("SELECT COUNT(*) AS n FROM patients")

        # encounters today/month/year (อิง encounter_date)
        today_patients = count_sql(
            """
            SELECT COUNT(DISTINCT patient_id) AS n
            FROM encounters
            WHERE encounter_date = CURDATE()
            """
        )

        month_patients = count_sql(
            """
            SELECT COUNT(DISTINCT patient_id) AS n
            FROM encounters
            WHERE YEAR(encounter_date) = YEAR(CURDATE())
              AND MONTH(encounter_date) = MONTH(CURDATE())
            """
        )

        year_patients = count_sql(
            """
            SELECT COUNT(DISTINCT patient_id) AS n
            FROM encounters
            WHERE YEAR(encounter_date) = YEAR(CURDATE())
            """
        )

        # pending patients (ยังไม่เคยมี encounter)
        pending_patients = count_sql(
            """
            SELECT COUNT(*) AS n
            FROM patients p
            LEFT JOIN encounters e ON e.patient_id = p.id
            WHERE e.id IS NULL
            """
        )

        # appointments today (ของหมอที่ login)
        doctor_id = session.get("user_id")
        today_appointments_count = count_sql(
            """
            SELECT COUNT(*) AS n
            FROM appointments
            WHERE DATE(appt_datetime) = CURDATE()
              AND status = 'scheduled'
              AND created_by_doctor = %s
            """,
            (doctor_id,),
        )

        # high risk (assessment_scores.risk_level)
        high_risk = count_sql(
            """
            SELECT COUNT(*) AS n
            FROM assessment_scores
            WHERE LOWER(risk_level) IN ('high','สูง','เสี่ยงสูง')
            """
        )

        # --------------------------
        # Quick filters + search (encounter_date)
        # --------------------------
        search_date_str = (request.args.get("search_date") or "").strip()
        search_month_str = (request.args.get("search_month") or "").strip()
        search_year_str = (request.args.get("search_year") or "").strip()
        quick = (request.args.get("quick") or "").strip()

        week_start_str = (request.args.get("week_start") or "").strip()
        week_end_str = (request.args.get("week_end") or "").strip()

        date_patient_count = None
        date_label_th = ""
        month_patient_count = None
        month_label_th = ""
        year_patient_count = None
        year_label_th = ""

        today = date.today()

        if quick == "today":
            search_date_str = today.strftime("%Y-%m-%d")
            week_start_str = ""
            week_end_str = ""
        elif quick == "week":
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            search_date_str = monday.strftime("%Y-%m-%d")
            week_start_str = monday.strftime("%Y-%m-%d")
            week_end_str = sunday.strftime("%Y-%m-%d")
        elif quick == "month":
            search_month_str = today.strftime("%Y-%m")
        elif quick == "year":
            search_year_str = str(today.year)

        # by week / day
        if week_start_str and week_end_str:
            try:
                monday = datetime.strptime(week_start_str, "%Y-%m-%d").date()
                sunday = datetime.strptime(week_end_str, "%Y-%m-%d").date()
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT patient_id) AS c
                    FROM encounters
                    WHERE encounter_date BETWEEN %s AND %s
                    """,
                    (monday, sunday),
                )
                date_patient_count = int(((cur.fetchone() or {}).get("c") or 0))
                date_label_th = f"ระหว่าง {format_thai_short_with_year(monday)} – {format_thai_short_with_year(sunday)}"
            except ValueError:
                pass
        elif search_date_str:
            try:
                selected_date = datetime.strptime(search_date_str, "%Y-%m-%d").date()
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT patient_id) AS c
                    FROM encounters
                    WHERE encounter_date = %s
                    """,
                    (selected_date,),
                )
                date_patient_count = int(((cur.fetchone() or {}).get("c") or 0))
                date_label_th = f"ประเมิน {format_thai_short_with_year(selected_date)}"
            except ValueError:
                pass

        # by month
        if search_month_str:
            try:
                y, m = map(int, search_month_str.split("-"))
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT patient_id) AS c
                    FROM encounters
                    WHERE YEAR(encounter_date) = %s AND MONTH(encounter_date) = %s
                    """,
                    (y, m),
                )
                month_patient_count = int(((cur.fetchone() or {}).get("c") or 0))
                month_label_th = f"{_thai_months_full()[m-1]} {y + 543}"
            except (ValueError, IndexError):
                pass

        # by year
        if search_year_str:
            try:
                yr = int(search_year_str)
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT patient_id) AS c
                    FROM encounters
                    WHERE YEAR(encounter_date) = %s
                    """,
                    (yr,),
                )
                year_patient_count = int(((cur.fetchone() or {}).get("c") or 0))
                year_label_th = str(yr + 543)
            except ValueError:
                pass

        # --------------------------
        # Latest encounters (5) - ใช้ created_at เรียงล่าสุด
        # --------------------------
        cur.execute(
            """
            SELECT
                p.id AS patient_id,
                p.hn,
                p.full_name,
                e.encounter_date,
                e.created_at
            FROM encounters e
            JOIN patients p ON p.id = e.patient_id
            ORDER BY e.created_at DESC
            LIMIT 5
            """
        )
        latest_rows = cur.fetchall() or []
        latest_assessments = []
        for r in latest_rows:
            nm = (r.get("full_name") or "-").strip() or "-"
            d = r.get("encounter_date")
            initials = nm[0] if nm and nm != "-" else "ผ"
            latest_assessments.append(
                {
                    "patient_id": r.get("patient_id"),
                    "hn": r.get("hn") or "-",
                    "name": nm,
                    "initials": initials,
                    "date_th": format_thai_short_with_year(d) if d else "-",
                }
            )

        # --------------------------
        # Today appointments list (10)
        # --------------------------
        cur.execute(
            """
            SELECT
                a.patient_id,
                p.full_name,
                a.appt_datetime,
                a.note
            FROM appointments a
            JOIN patients p ON p.id = a.patient_id
            WHERE DATE(a.appt_datetime) = CURDATE()
              AND a.status = 'scheduled'
              AND a.created_by_doctor = %s
            ORDER BY a.appt_datetime ASC
            LIMIT 10
            """,
            (doctor_id,),
        )
        appts_raw = cur.fetchall() or []
        today_appointments = []
        for a in appts_raw:
            appt_time = a.get("appt_datetime")
            today_appointments.append(
                {
                    "patient_id": a.get("patient_id"),
                    "name": (a.get("full_name") or "-").strip() or "-",
                    "time": appt_time.strftime("%H:%M") if appt_time else "--:--",
                    "note": a.get("note") or "-",
                }
            )

        # --------------------------
        # Charts
        # --------------------------
        cur.execute(
            """
            SELECT
                CASE
                    WHEN LOWER(risk_level) IN ('low','ปกติ') THEN 'ปกติ'
                    WHEN LOWER(risk_level) IN ('medium','เสี่ยง') THEN 'เสี่ยง'
                    WHEN LOWER(risk_level) IN ('high','สูง','เสี่ยงสูง') THEN 'ผิดปกติ'
                    ELSE 'ปกติ'
                END AS risk_category,
                COUNT(*) AS count
            FROM assessment_scores
            WHERE instrument = 'MMSE'
            GROUP BY risk_category
            """
        )
        risk_raw = cur.fetchall() or []
        risk_dict = {r["risk_category"]: int(r["count"]) for r in risk_raw}
        risk_labels = ["ปกติ", "เสี่ยง", "ผิดปกติ"]
        risk_data = [risk_dict.get(lb, 0) for lb in risk_labels]

        cur.execute(
            """
            SELECT
              CASE
                WHEN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) BETWEEN 60 AND 64 THEN '60-64'
                WHEN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) BETWEEN 65 AND 69 THEN '65-69'
                WHEN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) BETWEEN 70 AND 74 THEN '70-74'
                WHEN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) BETWEEN 75 AND 79 THEN '75-79'
                WHEN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) >= 80 THEN '80+'
                ELSE 'อื่นๆ'
              END AS age_group,
              COUNT(*) AS count
            FROM patients
            WHERE birth_date IS NOT NULL
              AND TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) >= 60
            GROUP BY age_group
            """
        )
        age_raw = cur.fetchall() or []
        age_dict = {r["age_group"]: int(r["count"]) for r in age_raw}
        age_labels = ["60-64", "65-69", "70-74", "75-79", "80+"]
        age_data = [age_dict.get(lb, 0) for lb in age_labels]

        cur.execute(
            """
            SELECT
                MONTH(encounter_date) AS month,
                COUNT(DISTINCT patient_id) AS patient_count
            FROM encounters
            WHERE YEAR(encounter_date) = YEAR(CURDATE())
            GROUP BY MONTH(encounter_date)
            ORDER BY MONTH(encounter_date)
            """
        )
        monthly_raw = cur.fetchall() or []
        monthly_dict = {int(r["month"]): int(r["patient_count"]) for r in monthly_raw}
        monthly_labels = _thai_months_short()
        monthly_data = [monthly_dict.get(i, 0) for i in range(1, 13)]

        cur.execute(
            """
            SELECT AVG(TIMESTAMPDIFF(YEAR, birth_date, CURDATE())) AS avg_age
            FROM patients
            WHERE birth_date IS NOT NULL
            """
        )
        avg_age = float((cur.fetchone() or {}).get("avg_age") or 0)

        cur.execute(
            """
            SELECT COUNT(*) / NULLIF(COUNT(DISTINCT patient_id), 0) AS avg_assess
            FROM encounters
            """
        )
        avg_assessment = float((cur.fetchone() or {}).get("avg_assess") or 0)

        total_risk = sum(risk_data) or 1
        risk_rate = ((risk_data[1] + risk_data[2]) * 100.0) / total_risk


        # avg score เดือนนี้
        cur.execute("""
            SELECT AVG(total_score) AS avg_score
            FROM assessment_scores
            WHERE total_score IS NOT NULL
            AND YEAR(computed_at) = YEAR(CURDATE())
            AND MONTH(computed_at) = MONTH(CURDATE())
        """)
        avg_this_month = float((cur.fetchone() or {}).get("avg_score") or 0)

        # avg score เดือนที่แล้ว
        cur.execute("""
            SELECT AVG(total_score) AS avg_score
            FROM assessment_scores
            WHERE total_score IS NOT NULL
            AND YEAR(computed_at) = YEAR(DATE_SUB(CURDATE(), INTERVAL 1 MONTH))
            AND MONTH(computed_at) = MONTH(DATE_SUB(CURDATE(), INTERVAL 1 MONTH))
        """)
        avg_last_month = float((cur.fetchone() or {}).get("avg_score") or 0)

        avg_cga_score = avg_this_month  # ให้โชว์ avg เดือนนี้เป็นหลัก
        delta_avg_month = avg_this_month - avg_last_month

        kpis = {
            "total_patients": total_patients,
            "today_patients": today_patients,
            "month_patients": month_patients,
            "year_patients": year_patients,

            "pending_patients": pending_patients,
            "today_appointments": today_appointments_count,
            "high_risk": high_risk,

            "total_unique_patients": total_patients,
            "completed_patients_today": today_patients,

            "avg_cga_score": avg_cga_score,
            "delta_avg_month": delta_avg_month,
        }


        return render_template(
            "doctor/medical_dashboard.html",
            kpis=kpis,
            search_date=search_date_str,
            search_month=search_month_str,
            search_year=search_year_str,
            week_start=week_start_str,
            week_end=week_end_str,
            date_patient_count=date_patient_count,
            date_label_th=date_label_th,
            month_patient_count=month_patient_count,
            month_label_th=month_label_th,
            year_patient_count=year_patient_count,
            year_label_th=year_label_th,
            latest_assessments=latest_assessments,
            today_appointments=today_appointments,
            risk_labels=risk_labels,
            risk_data=risk_data,
            age_labels=age_labels,
            age_data=age_data,
            monthly_labels=monthly_labels,
            monthly_data=monthly_data,
            avg_age=round(avg_age, 1),
            avg_assessment=round(avg_assessment, 2),
            risk_rate=round(risk_rate, 1),
        )

    finally:
        cur.close()
        conn.close()


# ==============================
# Other pages (for navbar)
# ==============================
@doctor_bp.get("/patients")
def patients():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    return render_template("doctor/medical_patients.html")


@doctor_bp.get("/reports")
def reports():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    return render_template("doctor/medical_reports.html")


@doctor_bp.get("/assessments", endpoint="doctor_assessments")
def assessments():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    return redirect(url_for("doctor.patients"))


@doctor_bp.get("/duty")
def duty():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    return render_template("doctor/medical_doctorduty.html")


# =========================
# 1) GET: events for calendar
# endpoint name used in template: doctor.doctor_duty_events
# =========================
@doctor_bp.get("/duty/events", endpoint="doctor_duty_events")
def doctor_duty_events():
    if not _guard_doctor():
        return jsonify([]), 401

    doctor_id = session.get("user_id")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT
                id,
                title,
                start_datetime,
                end_datetime
            FROM doctor_duty_events
            WHERE doctor_id = %s
            ORDER BY start_datetime ASC
            """,
            (doctor_id,),
        )
        rows = cur.fetchall() or []

        events = []
        for r in rows:
            events.append(
                {
                    "id": r["id"],
                    "title": r["title"] or "ตารางเข้าเวร",
                    "start": r["start_datetime"].isoformat() if r["start_datetime"] else None,
                    "end": r["end_datetime"].isoformat() if r["end_datetime"] else None,
                }
            )

        return jsonify(events)
    finally:
        cur.close()
        conn.close()


# =========================
# 2) POST: create duty event
# template calling: url_for('doctor.doctor_duty_create')
# =========================
@doctor_bp.post("/duty/create", endpoint="doctor_duty_create")
def doctor_duty_create():
    if not _guard_doctor():
        return jsonify({"ok": False, "message": "unauthorized"}), 401

    doctor_id = session.get("user_id")

    # ===== 1) รับข้อมูลได้ทั้ง JSON และ FormData =====
    data = {}
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict(flat=True) or {}

    def pick(*keys, default=""):
        for k in keys:
            v = data.get(k)
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
                if v != "":
                    return v
            else:
                return v
        return default

    # ===== 2) ดึงค่าจากหลาย key ที่เป็นไปได้ =====
    # วันที่
    date_raw = pick(
        "date", "selected_date", "selectedDate", "duty_date", "dutyDate",
        "pickedDate", "day", "d", default=""
    )

    # เวลาเริ่ม/จบ (บาง UI ส่ง start/end เป็น "08:00")
    start_time = pick("start_time", "startTime", "time_start", "from", "from_time", default="")
    end_time   = pick("end_time", "endTime", "time_end", "to", "to_time", default="")

    # บางทีส่ง start/end เป็น datetime เต็ม
    start_dt_raw = pick("start_datetime", "start", "startDateTime", "start_datetime_iso", default="")
    end_dt_raw   = pick("end_datetime", "end", "endDateTime", "end_datetime_iso", default="")

    # ประเภทเวร/ชื่อเวร
    shift = pick("shift", "type", "duty_type", "dutyType", "title", default="Day")

    # note/location
    note = pick("note", "location", "place", "site", "room", "detail", default="")
    date_raw = pick(
        "date", "selected_date", "selectedDate", "duty_date", "dutyDate",
        "pickedDate", "day", "d", "shift_date",  # ✅ เพิ่มตัวนี้
        default=""
    )

    shift = pick("shift", "type", "duty_type", "dutyType", "title", "shift_type", default="Day")

    note = pick("note", "location", "place", "site", "room", "detail", default="")

    # ===== 3) แปลงเป็น datetime ให้ได้ =====
    def parse_iso(dt_str: str):
        # รับได้ทั้ง "2026-02-27T08:00:00+07:00" / "2026-02-27T08:00:00"
        if not dt_str:
            return None
        s = dt_str.strip()
        try:
            if s.endswith("Z"):
                s = s[:-1]
            if "+" in s:
                s = s.split("+", 1)[0]
            if s.count(":") == 1 and "T" in s:
                s = s + ":00"
            return datetime.fromisoformat(s)
        except Exception:
            return None

    start_dt = parse_iso(start_dt_raw)
    end_dt = parse_iso(end_dt_raw)

    if not start_dt:
        # ต้องมี date + start_time อย่างน้อย
        if not date_raw or not start_time:
            return jsonify({
                "ok": False,
                "message": "missing required fields",
                "need_one_of": ["start_datetime", "date + start_time"],
                "received": data
            }), 400
        try:
            start_dt = datetime.fromisoformat(f"{date_raw} {start_time}:00")
        except Exception:
            return jsonify({"ok": False, "message": "bad date/start_time", "received": data}), 400

    if not end_dt:
        # ถ้าไม่มี end_time ให้ตั้ง end = start (หรือ +8 ชม. ก็ได้ แต่เอาง่ายสุดก่อน)
        if end_time and date_raw:
            try:
                end_dt = datetime.fromisoformat(f"{date_raw} {end_time}:00")
            except Exception:
                end_dt = None
        if not end_dt:
            end_dt = start_dt

    # ===== 4) บันทึกลง DB =====
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            INSERT INTO doctor_duty_events (doctor_id, title, note, start_datetime, end_datetime)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (doctor_id, shift, note if note else None, start_dt, end_dt),
        )
        conn.commit()
        event_id = cur.lastrowid

        return jsonify({
            "ok": True,
            "id": event_id,
            "doctor_id": doctor_id,
            "title": shift,
            "note": note,
            "start_datetime": start_dt.isoformat(sep=" "),
            "end_datetime": end_dt.isoformat(sep=" "),
        })
    finally:
        cur.close()
        conn.close()
        
@doctor_bp.post("/duty/note/save", endpoint="doctor_duty_note_save")
def doctor_duty_note_save():
    if not _guard_doctor():
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    doctor_id = session.get("user_id")  # หรือ session.get("doctor_id") แล้วแต่ระบบคุณ
    if not doctor_id:
        return jsonify({"ok": False, "msg": "missing doctor session"}), 400

    # ✅ รับได้ทั้ง event_id / shift_id / id (กันชื่อไม่ตรง)
    event_id = (
        request.form.get("event_id")
        or request.form.get("shift_id")
        or request.form.get("id")
    )

    note = (request.form.get("note") or "").strip()

    if not event_id:
        return jsonify({
            "ok": False,
            "msg": "missing required fields",
            "need": ["shift_id (or event_id)", "note(optional)"],
            "received_keys": list(request.form.keys()),
        }), 400

    try:
        event_id = int(event_id)
    except ValueError:
        return jsonify({"ok": False, "msg": "invalid event_id"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE doctor_duty_events
            SET note = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND doctor_id = %s
            """,
            (note if note else None, event_id, doctor_id),
        )
        conn.commit()

        if cur.rowcount == 0:
            return jsonify({"ok": False, "msg": "not found or not owner"}), 404

        return jsonify({"ok": True})
    finally:
        cur.close()
        conn.close()
        
@doctor_bp.post("/duty/delete", endpoint="doctor_duty_delete")
def doctor_duty_delete():
    if not _guard_doctor():
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    doctor_id = session.get("user_id")
    shift_id = (request.form.get("shift_id") or "").strip()

    if not shift_id.isdigit():
        return jsonify({"ok": False, "msg": "shift_id ไม่ถูกต้อง"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # ลบได้เฉพาะของหมอคนนั้น
        cur.execute(
            "DELETE FROM doctor_duty_events WHERE id=%s AND doctor_id=%s",
            (int(shift_id), int(doctor_id)),
        )
        conn.commit()

        if cur.rowcount == 0:
            return jsonify({"ok": False, "msg": "ไม่พบเวร หรือไม่มีสิทธิ์ลบ"}), 404

        return jsonify({"ok": True})
    finally:
        cur.close()
        conn.close()