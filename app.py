from __future__ import annotations

import os
import io
import csv
from datetime import datetime, date, timedelta

import joblib
import mysql.connector  # type: ignore
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    make_response,
    abort,
)
from werkzeug.security import check_password_hash


# =========================================================
# ML Model (safe load)
# =========================================================
try:
    model = joblib.load("naive_bayes_cga.pkl")
    label_encoder = joblib.load("naive_bayes_label_encoder.pkl")
except Exception as e:
    print("❌ Load model failed:", e)
    model = None
    label_encoder = None


def predict_risk(features):
    """
    features = [mmse, tgds, sra, edu, age] (ตัวอย่าง)
    """
    if model is None or label_encoder is None:
        return "model_not_loaded"
    pred = model.predict([features])
    return label_encoder.inverse_transform(pred)[0]


# =========================================================
# Database Connection (SAFE)
# =========================================================
def get_db_connection():
    """
    ✅ แนะนำตั้ง env:
      set DB_HOST=localhost
      set DB_USER=root
      set DB_PASSWORD=xxxx
      set DB_NAME=cga_system
      set DB_PORT=3306
    """
    host = os.environ.get("DB_HOST", "localhost")
    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD", "")
    dbname = os.environ.get("DB_NAME", "cga_system")
    port = int(os.environ.get("DB_PORT", "3306"))

    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=dbname,
            port=port,
            connection_timeout=10,
            autocommit=False,
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
        return None


# =========================================================
# Helpers
# =========================================================
def require_role(role_code: str) -> bool:
    return session.get("role") == role_code


def sex_th(sex_code: str | None) -> str:
    # schema: patients.sex = 'M','F','O'
    if sex_code == "M":
        return "ชาย"
    if sex_code == "F":
        return "หญิง"
    if sex_code == "O":
        return "อื่นๆ"
    return "-"


def _thai_months_short():
    return ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _thai_months_full():
    return [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]


def format_thai_short_with_year(d: date) -> str:
    thai_year_2 = str(d.year + 543)[-2:]
    return f"{d.day}/{d.month}/{thai_year_2}"


def format_thai_full(d: date) -> str:
    months = _thai_months_full()
    return f"{d.day} {months[d.month - 1]} {d.year + 543}"


def calc_age_from_birthdate(birth_date: date | None) -> int | None:
    if not birth_date:
        return None
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age


def patient_display_name(p: dict) -> str:
    fn = (p.get("first_name") or "").strip()
    ln = (p.get("last_name") or "").strip()
    full = f"{fn} {ln}".strip()
    return full or "-"


def build_address_text(p: dict) -> str:
    parts = []
    if p.get("address_no"):
        parts.append(f"บ้านเลขที่ {p['address_no']}")
    if p.get("address_moo"):
        parts.append(f"หมู่ {p['address_moo']}")
    if p.get("address_tambon"):
        parts.append(f"ต.{p['address_tambon']}")
    if p.get("address_amphoe"):
        parts.append(f"อ.{p['address_amphoe']}")
    if p.get("address_province"):
        parts.append(f"จ.{p['address_province']}")
    return " ".join(parts) if parts else "-"


def risk_from_scores(mmse: float | None, tgds: float | None, q8: float | None):
    """
    rule เดิมแบบง่าย:
    - เสี่ยงสูง: q8>=9 หรือ tgds>=6 หรือ mmse<=21
    - เสี่ยงปานกลาง: q8>0 หรือ tgds>=4 หรือ mmse<=26
    - ไม่งั้นเสี่ยงต่ำ
    """
    mmse_v = float(mmse or 0)
    tgds_v = float(tgds or 0)
    q8_v = float(q8 or 0)

    if q8_v >= 9 or tgds_v >= 6 or mmse_v <= 21:
        return ("เสี่ยงสูง", "high")
    elif q8_v > 0 or tgds_v >= 4 or mmse_v <= 26:
        return ("เสี่ยงปานกลาง", "medium")
    return ("เสี่ยงต่ำ", "low")


def fetch_user_by_username(username: str):
    conn = get_db_connection()
    if not conn:
        return None

    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT
            u.id,
            u.username,
            u.password_hash,
            u.full_name,
            u.is_active,
            r.role_code
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.username = %s
        LIMIT 1
        """,
        (username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def log_audit(user_id: int | None, action: str, entity: str | None = None, entity_id: int | None = None, detail=None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_logs (user_id, action, entity, entity_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, action, entity or "-", entity_id, detail),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def dt_local_to_sql(s: str | None) -> str | None:
    # "2026-01-18T22:30" -> "2026-01-18 22:30:00"
    if not s:
        return None
    if "T" in s and len(s) >= 16:
        return s.replace("T", " ") + ":00"
    return s


def get_patient_by_hn_gcn(hn: str, gcn: str):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM patients WHERE hn=%s AND gcn=%s LIMIT 1", (hn, gcn))
    p = cur.fetchone()
    cur.close()
    conn.close()
    return p


def get_patient_id_by_hn_gcn(hn: str, gcn: str) -> int | None:
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM patients WHERE hn=%s AND gcn=%s LIMIT 1", (hn, gcn))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return int(row["id"]) if row and row.get("id") is not None else None


# =========================================================
# Flask App
# =========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")


# Blueprint (admin)
try:
    from admin.routes_admin import admin_bp
    app.register_blueprint(admin_bp)
except Exception as e:
    print("⚠️ admin blueprint load failed:", e)


# =========================================================
# Index
# =========================================================
@app.route("/")
def index():
    return redirect(url_for("doctor_login"))


# =========================================================
# Doctor Login/Logout
# =========================================================
@app.route("/doctor/login", methods=["GET", "POST"])
def doctor_login():
    if request.method == "GET":
        return render_template("medical_login.html")

    session.clear()

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    user = fetch_user_by_username(username)
    if not user:
        flash("ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง", "error")
        return render_template("medical_login.html")

    if not user.get("is_active", 1):
        flash("บัญชีถูกปิดการใช้งาน", "error")
        return render_template("medical_login.html")

    if user.get("role_code") != "doctor":
        flash("บัญชีนี้ไม่ใช่แพทย์", "error")
        return render_template("medical_login.html")

    if not check_password_hash(user["password_hash"], password):
        flash("ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง", "error")
        return render_template("medical_login.html")

    session["user_id"] = user["id"]
    session["role"] = "doctor"
    session["username"] = user["username"]
    session["doctor_id"] = user["id"]
    session["doctor_name"] = user["full_name"]

    log_audit(user["id"], "LOGIN", "users", user["id"])
    return redirect(url_for("doctor_dashboard"))


@app.route("/logout")
def logout():
    uid = session.get("doctor_id")
    session.clear()
    if uid:
        log_audit(uid, "LOGOUT", "users", uid)
    return redirect(url_for("doctor_login"))


# =========================================================
# Doctor Dashboard
# =========================================================
@app.route("/doctor")
def doctor_index():
    return redirect(url_for("doctor_dashboard"))


@app.route("/doctor/dashboard")
def doctor_dashboard():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_login"))

    cur = conn.cursor(dictionary=True)

    # จำนวนผู้ป่วยทั้งหมด (unique patients)
    cur.execute("SELECT COUNT(DISTINCT id) AS total FROM patients")
    total_patients = (cur.fetchone() or {}).get("total", 0) or 0

    # ผู้ป่วยที่มีการประเมินวันนี้ (unique patients today)
    cur.execute("""
        SELECT COUNT(DISTINCT patient_id) AS today
        FROM encounters
        WHERE DATE(encounter_datetime) = CURDATE()
    """)
    today_patients = (cur.fetchone() or {}).get("today", 0) or 0

    # ผู้ป่วยที่มีการประเมินเดือนนี้ (unique patients this month)
    cur.execute("""
        SELECT COUNT(DISTINCT patient_id) AS month
        FROM encounters
        WHERE YEAR(encounter_datetime) = YEAR(CURDATE())
          AND MONTH(encounter_datetime) = MONTH(CURDATE())
    """)
    month_patients = (cur.fetchone() or {}).get("month", 0) or 0

    # ผู้ป่วยที่มีการประเมินปีนี้ (unique patients this year)
    cur.execute("""
        SELECT COUNT(DISTINCT patient_id) AS year
        FROM encounters
        WHERE YEAR(encounter_datetime) = YEAR(CURDATE())
    """)
    year_patients = (cur.fetchone() or {}).get("year", 0) or 0

    # ========================================
    # Query Parameters สำหรับการค้นหา
    # ========================================
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

    # Quick filters
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

    # นับผู้ป่วยตามวัน/สัปดาห์
    if week_start_str and week_end_str:
        try:
            monday = datetime.strptime(week_start_str, "%Y-%m-%d").date()
            sunday = datetime.strptime(week_end_str, "%Y-%m-%d").date()
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE DATE(encounter_datetime) BETWEEN %s AND %s
            """, (monday, sunday))
            date_patient_count = (cur.fetchone() or {}).get("c", 0) or 0
            date_label_th = f"ระหว่าง {format_thai_short_with_year(monday)} – {format_thai_short_with_year(sunday)}"
        except ValueError:
            pass
    elif search_date_str:
        try:
            selected_date = datetime.strptime(search_date_str, "%Y-%m-%d").date()
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE DATE(encounter_datetime) = %s
            """, (selected_date,))
            date_patient_count = (cur.fetchone() or {}).get("c", 0) or 0
            date_label_th = f"ประเมิน {format_thai_short_with_year(selected_date)}"
        except ValueError:
            pass

    # นับผู้ป่วยตามเดือน
    if search_month_str:
        try:
            y, m = map(int, search_month_str.split("-"))
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE YEAR(encounter_datetime) = %s AND MONTH(encounter_datetime) = %s
            """, (y, m))
            month_patient_count = (cur.fetchone() or {}).get("c", 0) or 0
            month_label_th = f"{_thai_months_full()[m-1]} {y + 543}"
        except (ValueError, IndexError):
            pass

    # นับผู้ป่วยตามปี
    if search_year_str:
        try:
            yr = int(search_year_str)
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE YEAR(encounter_datetime) = %s
            """, (yr,))
            year_patient_count = (cur.fetchone() or {}).get("c", 0) or 0
            year_label_th = str(yr + 543)
        except ValueError:
            pass

    # ========================================
    # KPI Cards กลาง
    # ========================================
    total_unique_patients = total_patients
    completed_patients_today = today_patients

    cur.execute("""
        SELECT COUNT(DISTINCT p.id) AS pending
        FROM patients p
        LEFT JOIN encounters e ON e.patient_id = p.id
        WHERE e.id IS NULL
    """)
    pending_patients = (cur.fetchone() or {}).get("pending", 0) or 0

    cur.execute("""
        SELECT AVG(ah.total_score) AS avg_score
        FROM assessment_headers ah
        WHERE ah.form_code = 'MMSE'
          AND ah.total_score IS NOT NULL
    """)
    avg_cga_score = float((cur.fetchone() or {}).get("avg_score") or 0)

    cur.execute("""
        SELECT COUNT(DISTINCT patient_id) AS last_month
        FROM encounters
        WHERE YEAR(encounter_datetime) = YEAR(DATE_SUB(CURDATE(), INTERVAL 1 MONTH))
          AND MONTH(encounter_datetime) = MONTH(DATE_SUB(CURDATE(), INTERVAL 1 MONTH))
    """)
    last_month_patients = (cur.fetchone() or {}).get("last_month", 0) or 0
    delta_patients_month = month_patients - last_month_patients

    cur.execute("""
        SELECT COUNT(DISTINCT patient_id) AS last_week
        FROM encounters
        WHERE YEARWEEK(encounter_datetime, 1) = YEARWEEK(DATE_SUB(CURDATE(), INTERVAL 1 WEEK), 1)
    """)
    last_week_patients = (cur.fetchone() or {}).get("last_week", 0) or 0
    delta_completed_week = today_patients - last_week_patients

    # ========================================
    # การประเมินล่าสุด
    # ========================================
    cur.execute("""
        SELECT
            p.id AS patient_id,
            p.hn,
            p.gcn,
            p.first_name,
            p.last_name,
            e.encounter_datetime,
            ah.total_score
        FROM encounters e
        JOIN patients p ON p.id = e.patient_id
        LEFT JOIN assessment_headers ah
          ON ah.encounter_id = e.id AND ah.form_code = 'MMSE'
        ORDER BY e.encounter_datetime DESC
        LIMIT 5
    """)
    latest_assessments_raw = cur.fetchall() or []

    latest_assessments = []
    for r in latest_assessments_raw:
        name = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip()
        initials = name[0] if name else "ผ"
        enc_dt = r.get("encounter_datetime")

        latest_assessments.append({
            "patient_id": r.get("patient_id"),
            "hn": r.get("hn") or "-",
            "gcn": r.get("gcn") or "-",
            "name": name or "-",
            "initials": initials,
            "score": int(r.get("total_score") or 0),
            "date_th": format_thai_short_with_year(enc_dt.date()) if enc_dt else "-",
        })

    # ✅ นัดหมายวันนี้ (อยู่นอก loop)
    cur.execute("""
        SELECT
            a.patient_id,
            p.first_name,
            p.last_name,
            a.appt_datetime,
            a.reason
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE DATE(a.appt_datetime) = CURDATE()
          AND a.status = 'scheduled'
        ORDER BY a.appt_datetime ASC
        LIMIT 10
    """)
    appts_raw = cur.fetchall() or []

    today_appointments = []
    for a in appts_raw:
        name = f"{(a.get('first_name') or '').strip()} {(a.get('last_name') or '').strip()}".strip()
        appt_time = a.get("appt_datetime")
        today_appointments.append({
            "patient_id": a.get("patient_id"),
            "name": name or "-",
            "time": appt_time.strftime("%H:%M") if appt_time else "--:--",
            "note": a.get("reason") or "-",
        })

    # ========================================
    # Charts
    # ========================================
    cur.execute("""
        SELECT
          CASE
            WHEN ah.result_text LIKE '%ปกติ%' THEN 'ปกติ'
            WHEN ah.result_text LIKE '%เสี่ยง%' OR ah.result_text LIKE '%สงสัย%' THEN 'เสี่ยง'
            WHEN ah.result_text LIKE '%ผิดปกติ%' OR ah.result_text LIKE '%สมองเสื่อม%' THEN 'ผิดปกติ'
            ELSE 'ปกติ'
          END AS risk_category,
          COUNT(*) AS count
        FROM assessment_headers ah
        WHERE ah.form_code = 'MMSE'
        GROUP BY risk_category
    """)
    risk_raw = cur.fetchall() or []
    risk_dict = {r["risk_category"]: int(r["count"]) for r in risk_raw}

    risk_labels = ["ปกติ", "เสี่ยง", "ผิดปกติ"]
    risk_data = [risk_dict.get(label, 0) for label in risk_labels]

    cur.execute("""
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
    """)
    age_raw = cur.fetchall() or []
    age_dict = {r["age_group"]: int(r["count"]) for r in age_raw}

    age_labels = ["60-64", "65-69", "70-74", "75-79", "80+"]
    age_data = [age_dict.get(label, 0) for label in age_labels]

    cur.execute("""
        SELECT
            MONTH(encounter_datetime) AS month,
            COUNT(DISTINCT patient_id) AS patient_count
        FROM encounters
        WHERE YEAR(encounter_datetime) = YEAR(CURDATE())
        GROUP BY MONTH(encounter_datetime)
        ORDER BY MONTH(encounter_datetime)
    """)
    monthly_raw = cur.fetchall() or []
    monthly_dict = {int(r["month"]): int(r["patient_count"]) for r in monthly_raw}

    monthly_labels = _thai_months_short()
    monthly_data = [monthly_dict.get(i, 0) for i in range(1, 13)]

    # Statistics
    cur.execute("""
        SELECT AVG(TIMESTAMPDIFF(YEAR, birth_date, CURDATE())) AS avg_age
        FROM patients
        WHERE birth_date IS NOT NULL
    """)
    avg_age = float((cur.fetchone() or {}).get("avg_age") or 0)

    cur.execute("""
        SELECT COUNT(*) / NULLIF(COUNT(DISTINCT patient_id), 0) AS avg_assess
        FROM encounters
    """)
    avg_assessment = float((cur.fetchone() or {}).get("avg_assess") or 0)

    total_risk = sum(risk_data) or 1
    risk_rate = ((risk_data[1] + risk_data[2]) * 100.0) / total_risk

    cur.close()
    conn.close()

    kpis = {
        "total_patients": total_patients,
        "today_patients": today_patients,
        "month_patients": month_patients,
        "year_patients": year_patients,

        "total_unique_patients": total_unique_patients,
        "delta_patients_month": delta_patients_month,

        "completed_patients_today": completed_patients_today,
        "delta_completed_week": delta_completed_week,

        "pending_patients": pending_patients,
        "delta_pending_week_text": f"{delta_completed_week:+d} จากสัปดาห์ที่แล้ว",

        "avg_cga_score": round(avg_cga_score, 2),
        "delta_avg_month": 0.0,
    }

    return render_template(
        "medical_dashboard.html",
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


# =========================================================
# Doctor Assessments List
# =========================================================
@app.route("/doctor/assessments")
def doctor_assessments():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template("medical_assessments.html", assessments=[])

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            p.id AS patient_id,
            p.hn,
            p.gcn,
            p.first_name,
            p.last_name,
            e.encounter_datetime,
            ah.total_score,
            ah.result_text
        FROM encounters e
        JOIN patients p ON p.id = e.patient_id
        LEFT JOIN assessment_headers ah ON ah.encounter_id = e.id
            AND ah.form_code = 'MMSE'
        ORDER BY e.encounter_datetime DESC
        LIMIT 50
    """)
    rows = cur.fetchall() or []

    assessments = []
    for r in rows:
        name = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip()
        assessments.append({
            "patient_id": r.get("patient_id"),
            "hn": r.get("hn") or "-",
            "gcn": r.get("gcn") or "-",
            "name": name or "-",
            "score": int(r.get("total_score") or 0),
            "result": r.get("result_text") or "-",
            "date": r.get("encounter_datetime"),
        })

    cur.close()
    conn.close()
    return render_template("medical_assessments.html", assessments=assessments)


# =========================================================
# Doctor Patients (list) - uses visits + assessment_* tables
# =========================================================
@app.route("/doctor/patients")
def doctor_patients():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))

    search_date = (request.args.get("search_date") or "").strip()
    week_start = (request.args.get("week_start") or "").strip()
    week_end = (request.args.get("week_end") or "").strip()
    search_month = (request.args.get("search_month") or "").strip()
    search_year = (request.args.get("search_year") or "").strip()

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template("medical_patients.html", patients=[])

    cur = conn.cursor(dictionary=True)

    def _cols(table_name: str) -> set[str]:
        cur.execute(
            """
            SELECT COLUMN_NAME AS column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table_name,),
        )
        out = set()
        for r in (cur.fetchall() or []):
            out.add(r.get("column_name") or r.get("COLUMN_NAME"))
        return {c for c in out if c}

    def _pick(cols: set[str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in cols:
                return c
        return None

    sql = """
        SELECT
            p.id AS patient_id,
            p.hn,
            p.gcn,
            p.first_name,
            p.last_name,
            p.sex,
            p.birth_date,
            p.age_years,
            v.id AS visit_id,
            v.created_at AS last_assessed_date
        FROM patients p
        JOIN visits v ON v.patient_id = p.id
        JOIN (
            SELECT patient_id, MAX(created_at) AS max_visit
            FROM visits
            GROUP BY patient_id
        ) lv ON lv.patient_id = v.patient_id AND lv.max_visit = v.created_at
        WHERE 1=1
    """
    params = []

    if week_start and week_end:
        sql += " AND DATE(v.created_at) BETWEEN %s AND %s"
        params.extend([week_start, week_end])
    elif search_date:
        sql += " AND DATE(v.created_at) = %s"
        params.append(search_date)
    elif search_month:
        y, m = search_month.split("-")
        sql += " AND YEAR(v.created_at) = %s AND MONTH(v.created_at) = %s"
        params.extend([int(y), int(m)])
    elif search_year:
        sql += " AND YEAR(v.created_at) = %s"
        params.append(int(search_year))

    sql += " ORDER BY v.created_at DESC"

    cur.execute(sql, params)
    rows = cur.fetchall() or []
    visit_ids = [r["visit_id"] for r in rows if r.get("visit_id")]

    mmse_map = {}
    tgds_map = {}
    sra_map = {}
    sra_level_map = {}
    q2_map = {}

    if visit_ids:
        ph = ",".join(["%s"] * len(visit_ids))

        # MMSE
        cur.execute(
            f"""
            SELECT visit_id, score_total
            FROM assessment_mmse
            WHERE visit_id IN ({ph})
            """,
            visit_ids,
        )
        for r in cur.fetchall() or []:
            mmse_map[r["visit_id"]] = r.get("score_total")

        # TGDS-15 detect col
        tgds_cols = _cols("assessment_tgds15")
        tgds_score_col = _pick(tgds_cols, ["total_score", "score_total", "total_sum", "total", "score"])
        if tgds_score_col:
            cur.execute(
                f"""
                SELECT visit_id, {tgds_score_col} AS score
                FROM assessment_tgds15
                WHERE visit_id IN ({ph})
                """,
                visit_ids,
            )
            for r in cur.fetchall() or []:
                tgds_map[r["visit_id"]] = r.get("score")

        # 8Q
        cur.execute(
            f"""
            SELECT visit_id, total_score, risk_level
            FROM assessment_8q
            WHERE visit_id IN ({ph})
            """,
            visit_ids,
        )
        for r in cur.fetchall() or []:
            sra_map[r["visit_id"]] = r.get("total_score")
            sra_level_map[r["visit_id"]] = r.get("risk_level")

        # 2Q
        cur.execute(
            f"""
            SELECT visit_id, yes_count
            FROM assessment_depression_2q
            WHERE visit_id IN ({ph})
            """,
            visit_ids,
        )
        for r in cur.fetchall() or []:
            q2_map[r["visit_id"]] = r.get("yes_count")

    patients = []
    for r in rows:
        birth = r.get("birth_date")
        age = r.get("age_years")
        if age is None and isinstance(birth, date):
            age = calc_age_from_birthdate(birth)

        vid = r.get("visit_id")
        name = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip() or "-"

        patients.append({
            "patient_id": r.get("patient_id"),
            "hn": r.get("hn") or "-",
            "gcn": r.get("gcn") or "-",
            "name": name,
            "age": age if age is not None else "-",
            "gender": sex_th(r.get("sex")),
            "disease": None,
            "last_assessed_date": r.get("last_assessed_date"),

            "mmse": mmse_map.get(vid),
            "tgds": tgds_map.get(vid),
            "sra": sra_map.get(vid),
            "sra_level": sra_level_map.get(vid),
            "q2": q2_map.get(vid),
        })

    cur.close()
    conn.close()

    return render_template(
        "medical_patients.html",
        patients=patients,
        search_date=search_date,
        week_start=week_start,
        week_end=week_end,
        search_month=search_month,
        search_year=search_year,
    )


# =========================================================
# CGA General (view)
# =========================================================
@app.get("/doctor/patient/<hn>/<gcn>/cga-general", endpoint="doctor_cga_general_form")
def doctor_cga_general_form(hn, gcn):
    if session.get("role") != "doctor":
        return redirect(url_for("doctor_login"))

    patients = get_patient_by_hn_gcn(hn, gcn)
    if not patients:
        flash("ไม่พบผู้ป่วย", "error")
        return redirect(url_for("doctor_patients"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_patients"))
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT id
        FROM visits
        WHERE patient_id=%s
        ORDER BY visit_datetime DESC, id DESC
        LIMIT 1
    """, (patients["id"],))
    v = cur.fetchone()
    latest_visit_id = v["id"] if v else None

    cga_general = {}
    if latest_visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_cga_general
            WHERE visit_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        cga_general = cur.fetchone() or {}

    cur.close()
    conn.close()

    return render_template(
        "assess/cga_general_form.html",
        patients=patients,
        hn=hn,
        gcn=gcn,
        cga_general=cga_general,
    )


# =========================================================
# Delete patient (by hn) - keep as-is
# =========================================================
@app.post("/doctor/patients/<hn>/delete")
def doctor_patients_delete(hn):
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่ได้", "error")
        return redirect(url_for("doctor_patients"))

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM patients WHERE hn=%s", (hn,))
        conn.commit()
        flash(f"ลบผู้ป่วย HN {hn} เรียบร้อย", "success")
    except Exception as e:
        conn.rollback()
        flash(f"ลบไม่สำเร็จ: {e}", "error")
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

    return redirect(url_for("doctor_patients"))


# =========================================================
# Export CSV
# =========================================================
@app.route("/doctor/patients/export")
def doctor_patients_export():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))

    search_hn = (request.args.get("hn") or "").strip()
    search_name = (request.args.get("name") or "").strip()
    risk_filter = request.args.get("risk", "all")

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_patients"))

    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT
            p.hn,
            p.gcn,
            p.first_name,
            p.last_name,
            p.sex,
            p.birth_date,
            p.age_years,
            e.id AS encounter_id,
            e.encounter_datetime AS date_assessed,
            mmse.total_score AS mmse,
            tgds.total_score AS tgds,
            q8.total_score   AS q8
        FROM patients p
        LEFT JOIN (
            SELECT e1.*
            FROM encounters e1
            JOIN (
                SELECT patient_id, MAX(encounter_datetime) AS max_dt
                FROM encounters
                GROUP BY patient_id
            ) x
              ON x.patient_id = e1.patient_id AND x.max_dt = e1.encounter_datetime
        ) e ON e.patient_id = p.id
        LEFT JOIN assessment_headers mmse
          ON mmse.encounter_id = e.id AND mmse.form_code = 'MMSE'
        LEFT JOIN assessment_headers tgds
          ON tgds.encounter_id = e.id AND tgds.form_code = 'TGDS'
        LEFT JOIN assessment_headers q8
          ON q8.encounter_id = e.id AND q8.form_code = '8Q'
        WHERE 1=1
    """
    params = []
    if search_hn:
        sql += " AND p.hn LIKE %s"
        params.append(f"%{search_hn}%")
    if search_name:
        sql += " AND CONCAT(IFNULL(p.first_name,''), ' ', IFNULL(p.last_name,'')) LIKE %s"
        params.append(f"%{search_name}%")
    sql += " ORDER BY p.first_name, p.last_name"

    cur.execute(sql, params)
    rows = cur.fetchall() or []
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["HN", "GCN", "ชื่อ-นามสกุล", "อายุ", "เพศ", "MMSE", "TGDS", "8Q", "ความเสี่ยง"])

    for r in rows:
        age = r.get("age_years")
        if age is None and isinstance(r.get("birth_date"), date):
            age = calc_age_from_birthdate(r["birth_date"])

        mmse = r.get("mmse")
        tgds = r.get("tgds")
        q8 = r.get("q8")

        risk_text, risk_level = risk_from_scores(mmse, tgds, q8)
        if risk_filter in ("low", "medium", "high") and risk_level != risk_filter:
            continue

        name = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip()
        writer.writerow([
            r.get("hn") or "",
            r.get("gcn") or "",
            name,
            age or "",
            sex_th(r.get("sex")),
            int(mmse) if mmse is not None else 0,
            int(tgds) if tgds is not None else 0,
            int(q8) if q8 is not None else 0,
            risk_text,
        ])

    csv_data = output.getvalue()
    output.close()

    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=doctor_patients_export.csv"
    return response


# =========================================================
# Patient Detail (visits timeline) + assessments view
# =========================================================
@app.get("/doctor/patient/<hn>/<gcn>", endpoint="doctor_patient_detail")
def doctor_patient_detail(hn, gcn):
    if session.get("role") != "doctor":
        return redirect(url_for("doctor_login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_patients"))

    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT *
        FROM patients
        WHERE hn=%s AND gcn=%s
        LIMIT 1
    """, (hn, gcn))
    p = cur.fetchone()

    if not p:
        cur.close()
        conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("doctor_patients"))

    if (p.get("age_years") is None) and isinstance(p.get("birth_date"), date):
        p["age_years"] = calc_age_from_birthdate(p["birth_date"])

    patient_id = p["id"]

    # visits timeline
    cur.execute("""
        SELECT
            v.id,
            v.visit_datetime,
            v.chief_complaint,
            v.note,
            v.status,
            v.created_at,
            v.updated_at,
            (SELECT COUNT(*) FROM visit_diagnoses d WHERE d.visit_id = v.id) AS diag_count,
            (SELECT COUNT(*) FROM visit_notes n WHERE n.visit_id = v.id) AS note_count
        FROM visits v
        WHERE v.patient_id = %s
        ORDER BY v.visit_datetime DESC, v.id DESC
        LIMIT 50
    """, (patient_id,))
    visits = cur.fetchall() or []
    latest_visit_id = visits[0]["id"] if visits else None

    # upcoming appointments
    cur.execute("""
        SELECT a.id, a.appt_datetime, a.appt_type, a.location, a.reason, a.note, a.status
        FROM appointments a
        WHERE a.patient_id = %s
          AND a.status = 'scheduled'
        ORDER BY a.appt_datetime DESC
        LIMIT 20
    """, (patient_id,))
    upcoming_appts = cur.fetchall() or []

    # helper: detect tgds col
    def _cols(table_name: str) -> set[str]:
        cur.execute(
            """
            SELECT COLUMN_NAME AS column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table_name,),
        )
        out = set()
        for r in (cur.fetchall() or []):
            out.add(r.get("column_name") or r.get("COLUMN_NAME"))
        return {c for c in out if c}

    def _pick(cols: set[str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in cols:
                return c
        return None

    mmse = 0
    twoq = 0
    tgds = 0
    sra = 0
    sra_level = None

    if latest_visit_id:
        # MMSE
        cur.execute("""
            SELECT score_total
            FROM assessment_mmse
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        r = cur.fetchone()
        if r and r.get("score_total") is not None:
            mmse = int(r["score_total"])

        # 2Q
        cur.execute("""
            SELECT yes_count
            FROM assessment_depression_2q
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        r = cur.fetchone()
        if r and r.get("yes_count") is not None:
            twoq = int(r["yes_count"])

        # TGDS-15
        tgds_cols = _cols("assessment_tgds15")
        tgds_score_col = _pick(tgds_cols, ["total_score", "score_total", "total_sum", "total", "score"])
        if tgds_score_col:
            cur.execute(
                f"""
                SELECT {tgds_score_col} AS score
                FROM assessment_tgds15
                WHERE visit_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (latest_visit_id,),
            )
            r = cur.fetchone()
            if r and r.get("score") is not None:
                tgds = int(r["score"])

        # 8Q/SRA
        cur.execute("""
            SELECT total_score, risk_level
            FROM assessment_8q
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        r = cur.fetchone()
        if r:
            if r.get("total_score") is not None:
                sra = int(r["total_score"])
            sra_level = r.get("risk_level")

    # CGA GENERAL + hearing + vision
    cga_general = {}
    if latest_visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_cga_general
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        g = cur.fetchone() or {}

        cga_general = {
            "id": g.get("id"),
            "created_at": g.get("created_at"),
            "updated_at": g.get("updated_at"),

            "smoking_status": g.get("smoking_status") or g.get("smoking") or None,
            "smoking_per_day": g.get("smoking_per_day") or g.get("cig_per_day") or None,
            "quit_duration": g.get("quit_duration") or g.get("quit_text") or None,
            "alcohol_level": g.get("alcohol_level") or g.get("alcohol") or None,

            "chronic_diseases": g.get("chronic_diseases") or g.get("comorbidity_text") or None,
            "fall_history": g.get("fall_history") or g.get("fall") or None,
            "fall_count": g.get("fall_count") or None,

            "height": g.get("height") or g.get("height_cm"),
            "weight": g.get("weight") or g.get("weight_kg"),
            "waist": g.get("waist") or g.get("waist_cm"),
            "bmi": g.get("bmi"),

            "elderly_capacity": g.get("elderly_capacity") or g.get("capacity_group") or None,

            "note": g.get("note"),
            "remarks": g.get("remarks"),

            "urinary_incontinence": g.get("urinary_incontinence") or None,
            "urinary_referral": g.get("urinary_referral") or None,
            "sleep_problem": g.get("sleep_problem") or None,
            "sleep_referral": g.get("sleep_referral") or None,
        }

        # BMI calc
        try:
            h = float(cga_general.get("height") or 0)
            w = float(cga_general.get("weight") or 0)
            if (not cga_general.get("bmi")) and h > 0 and w > 0:
                cga_general["bmi"] = round(w / ((h / 100) ** 2), 1)
        except Exception:
            pass

        # HEARING
        cur.execute("""
            SELECT *
            FROM assessment_hearing
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        hh = cur.fetchone() or {}

        cga_general["hearing_left"] = hh.get("left_status") or hh.get("hearing_left") or None
        cga_general["hearing_right"] = hh.get("right_status") or hh.get("hearing_right") or None

        notes = []
        if hh.get("left_detail"):
            notes.append(f"ซ้าย: {hh['left_detail']}")
        if hh.get("right_detail"):
            notes.append(f"ขวา: {hh['right_detail']}")
        if hh.get("method"):
            notes.append(f"วิธี: {hh['method']}")
        cga_general["hearing_note"] = " | ".join(notes) if notes else None

        # VISION
        cur.execute("""
            SELECT *
            FROM assessment_vision
            WHERE visit_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (latest_visit_id,))
        vv = cur.fetchone() or {}

        if vv.get("left_numerator") is not None and vv.get("left_denominator") is not None:
            cga_general["vision_left_va"] = f"{vv['left_numerator']}/{vv['left_denominator']}"
        else:
            cga_general["vision_left_va"] = vv.get("vision_left_va") or None

        if vv.get("right_numerator") is not None and vv.get("right_denominator") is not None:
            cga_general["vision_right_va"] = f"{vv['right_numerator']}/{vv['right_denominator']}"
        else:
            cga_general["vision_right_va"] = vv.get("vision_right_va") or None

        cga_general["vision_left"] = vv.get("left_status") or vv.get("vision_left") or None
        cga_general["vision_right"] = vv.get("right_status") or vv.get("vision_right") or None
        cga_general["vision_note"] = vv.get("note") or None

    # risk from latest scores
    if (sra >= 9) or (tgds >= 6) or (mmse <= 21):
        risk_level, risk_text = "high", "เสี่ยงสูง"
    elif (sra > 0) or (tgds >= 4) or (mmse < 26):
        risk_level, risk_text = "medium", "เสี่ยงปานกลาง"
    else:
        risk_level, risk_text = "low", "เสี่ยงต่ำ"

    full_name = f"{(p.get('first_name') or '').strip()} {(p.get('last_name') or '').strip()}".strip()
    patients = {
        **p,
        "hn": p.get("hn"),
        "gcn": p.get("gcn"),
        "name": full_name or p.get("name") or "-",
        "age": p.get("age_years") if p.get("age_years") is not None else "-",
        "gender": sex_th(p.get("sex")),
        "phone": p.get("phone"),
        "address": p.get("address"),

        "mmse": mmse,
        "twoq": twoq,
        "tgds": tgds,
        "sra": sra,
        "sra_level": sra_level,
    }

    cur.close()
    conn.close()

    return render_template(
        "medical_patients_detail.html",
        patients=patients,
        visits=visits,
        upcoming_appts=upcoming_appts,
        _upcoming=upcoming_appts,
        cga_general=cga_general,
        risk_level=risk_level,
        risk_text=risk_text,
    )


# =========================================================
# Create Visit
# =========================================================
@app.post("/doctor/patient/<hn>/<gcn>/visit/create")
def doctor_visit_create(hn, gcn):
    patients = get_patient_by_hn_gcn(hn, gcn)
    if not patients:
        flash("ไม่พบผู้ป่วย", "error")
        return redirect(url_for("doctor_patients"))

    visit_dt = dt_local_to_sql(request.form.get("visit_datetime"))
    if not visit_dt:
        visit_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_id = session.get("user_id")
    role_code = session.get("role") or session.get("role_code")

    doctor_user_id = user_id if role_code in ["doctor", "DR"] else None
    nurse_user_id = user_id if role_code in ["nurse", "NR"] else None

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_patient_detail", hn=hn, gcn=gcn))

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO visits
          (patient_id, visit_datetime, nurse_user_id, doctor_user_id, chief_complaint, note, status, created_at, updated_at)
        VALUES
          (%s, %s, %s, %s, %s, %s, 'open', NOW(), NOW())
    """, (
        patients["id"],
        visit_dt,
        nurse_user_id,
        doctor_user_id,
        request.form.get("chief_complaint"),
        request.form.get("note"),
    ))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("doctor_patient_detail", hn=hn, gcn=gcn))


# =========================================================
# Modal: New Visit (embed)
# =========================================================
@app.get("/doctor/patient/<hn>/<gcn>/visit/new")
def doctor_visit_new_embed(hn, gcn):
    patients = get_patient_by_hn_gcn(hn, gcn)
    if not patients:
        return "<div class='text-rose-600'>ไม่พบผู้ป่วย</div>"
    return render_template("doctor/_visit_create_form.html", patients=patients)


# =========================================================
# Modal: Visit Detail (embed)
# =========================================================
@app.get("/doctor/visit/<int:visit_id>/embed")
def doctor_visit_embed(visit_id: int):
    conn = get_db_connection()
    if not conn:
        return "<div class='text-rose-600'>เชื่อมต่อฐานข้อมูลไม่สำเร็จ</div>"

    cur = conn.cursor(dictionary=True)

    # ✅ แก้ p.name -> CONCAT first_name/last_name ให้เรียบร้อย
    cur.execute("""
      SELECT
        v.*,
        p.hn,
        p.gcn,
        p.first_name,
        p.last_name,
        CONCAT(IFNULL(p.first_name,''),' ',IFNULL(p.last_name,'')) AS name
      FROM visits v
      JOIN patients p ON p.id = v.patient_id
      WHERE v.id=%s
    """, (visit_id,))
    visit = cur.fetchone()
    if not visit:
        cur.close()
        conn.close()
        return "<div class='text-rose-600'>ไม่พบ visit</div>"

    cur.execute("SELECT * FROM visit_diagnoses WHERE visit_id=%s ORDER BY id DESC", (visit_id,))
    diags = cur.fetchall() or []

    cur.execute("SELECT * FROM visit_notes WHERE visit_id=%s ORDER BY id DESC", (visit_id,))
    notes = cur.fetchall() or []

    cur.close()
    conn.close()
    return render_template("doctor/_visit_detail_embed.html", visit=visit, diags=diags, notes=notes)


@app.post("/doctor/visit/<int:visit_id>/diagnosis/add")
def doctor_visit_add_diag(visit_id: int):
    user_id = session.get("user_id")

    conn = get_db_connection()
    if not conn:
        return ("DB_ERROR", 500)

    cur = conn.cursor()
    cur.execute("""
      INSERT INTO visit_diagnoses (visit_id, diag_code, diag_name, diag_type, created_at, created_by)
      VALUES (%s,%s,%s,%s,NOW(),%s)
    """, (
      visit_id,
      request.form.get("diag_code"),
      request.form.get("diag_name"),
      request.form.get("diag_type") or "primary",
      user_id
    ))
    conn.commit()
    cur.close()
    conn.close()
    return ("OK", 200)


@app.post("/doctor/visit/<int:visit_id>/note/add")
def doctor_visit_add_note(visit_id: int):
    user_id = session.get("user_id")
    note_dt = dt_local_to_sql(request.form.get("note_datetime"))

    conn = get_db_connection()
    if not conn:
        return ("DB_ERROR", 500)

    cur = conn.cursor()
    cur.execute("""
      INSERT INTO visit_notes (visit_id, note_type, note_text, note_datetime, created_at, created_by)
      VALUES (%s,%s,%s,%s,NOW(),%s)
    """, (
      visit_id,
      request.form.get("note_type") or "general",
      request.form.get("note_text"),
      note_dt,
      user_id
    ))
    conn.commit()
    cur.close()
    conn.close()
    return ("OK", 200)


# =========================================================
# Modal: New Appointment (embed)
# =========================================================
@app.get("/doctor/patient/<hn>/<gcn>/appointment/new")
def doctor_appt_new_embed(hn, gcn):
    patients = get_patient_by_hn_gcn(hn, gcn)
    if not patients:
        return "<div class='text-rose-600'>ไม่พบผู้ป่วย</div>"
    return render_template("doctor/_appointment_form.html", patients=patients)


# =========================================================
# Appointment pages + create
# =========================================================
@app.route("/doctor/appointments")
def doctor_appointments():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))
    return render_template("medical_appointments.html")


@app.post("/doctor/patient/<hn>/<gcn>/appointment/create")
def doctor_appt_create(hn, gcn):
    if session.get("role") != "doctor":
        return redirect(url_for("doctor_login"))

    patients = get_patient_by_hn_gcn(hn, gcn)
    if not patients:
        flash("ไม่พบผู้ป่วย", "error")
        return redirect(url_for("doctor_patients"))

    appt_dt = dt_local_to_sql(request.form.get("appt_datetime"))
    if not appt_dt:
        flash("กรุณาระบุวันเวลานัด", "error")
        return redirect(url_for("doctor_patient_detail", hn=hn, gcn=gcn))

    user_id = session.get("user_id")

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("doctor_patient_detail", hn=hn, gcn=gcn))

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO appointments
              (
                patient_id,
                visit_id,
                appt_datetime,
                appt_type,
                location,
                reason,
                note,
                status,
                created_at,
                updated_at,
                created_by
              )
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, 'scheduled', NOW(), NOW(), %s)
        """, (
            patients["id"],
            request.form.get("visit_id") or None,
            appt_dt,
            request.form.get("appt_type"),
            request.form.get("location"),
            request.form.get("reason"),
            request.form.get("note"),
            user_id,
        ))
        conn.commit()
        flash("เพิ่มนัดเรียบร้อย", "success")
    except Exception as e:
        conn.rollback()
        flash(f"เพิ่มนัดไม่สำเร็จ: {e}", "error")
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

    return redirect(url_for("doctor_patient_detail", hn=hn, gcn=gcn))


# =========================================================
# Reports / Referrals pages
# =========================================================
@app.route("/doctor/reports")
def doctor_reports():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))
    return render_template("medical_reports.html")


@app.route("/doctor/referrals")
def doctor_referrals():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))
    return render_template("medical_referrals.html")


# =========================================================
# Duty Calendar
# =========================================================
@app.route("/doctor/duty")
def doctor_duty():
    if not require_role("doctor"):
        return redirect(url_for("doctor_login"))
    return render_template("medical_doctorduty.html")


def _color_for_shift(shift_type: str) -> str:
    # รองรับทั้ง UI (day/evening/night/oncall) และ DB enum (morning/afternoon/night/on_call)
    st = (shift_type or "").lower().replace("-", "").replace("_", "")
    if st in ("day", "morning"):
        return "#3b82f6"
    if st in ("evening", "afternoon"):
        return "#f59e0b"
    if st == "night":
        return "#ef4444"
    if st in ("oncall", "oncalll", "oncall", "oncallx", "oncallxx", "oncallxxx", "oncallxxxx", "oncallxxxxx", "oncallxxxxxx", "oncallxxxxxxx", "oncallxxxxxxxx"):
        return "#10b981"
    if st in ("oncall", "oncalll", "oncall", "oncallx"):
        return "#10b981"
    if st in ("oncall", "oncalll", "oncall"):
        return "#10b981"
    if st in ("oncall", "oncalll"):
        return "#10b981"
    if st in ("oncall",):
        return "#10b981"
    if st in ("oncall", "oncalll", "oncall", "oncallx", "oncallxx", "oncallxxx"):
        return "#10b981"
    if st in ("oncall", "oncalll", "oncall", "oncallx", "oncallxx", "oncallxxx", "oncallxxxx"):
        return "#10b981"
    if st in ("oncall", "oncalll", "oncall", "oncallx", "oncallxx", "oncallxxx", "oncallxxxx", "oncallxxxxx"):
        return "#10b981"
    if st in ("oncall", "on_call"):
        return "#10b981"
    return "#64748b"


@app.get("/doctor/api/duty-events", endpoint="doctor_duty_events")
def doctor_duty_events():
    if not require_role("doctor"):
        return jsonify([]), 401

    doctor_id = int(session.get("doctor_id") or 0)
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    try:
        start_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date() if start else date.today().replace(day=1)
        end_date = datetime.fromisoformat(end.replace("Z", "+00:00")).date() if end else (start_date + timedelta(days=31))
    except Exception:
        start_date = date.today().replace(day=1)
        end_date = start_date + timedelta(days=31)

    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, shift_date, shift_type, start_time, end_time, status, note, location
        FROM doctor_shifts
        WHERE doctor_user_id = %s
          AND shift_date BETWEEN %s AND %s
        ORDER BY shift_date ASC, start_time ASC
    """, (doctor_id, start_date, end_date))
    rows = cur.fetchall() or []
    cur.close()
    conn.close()

    events = []
    for r in rows:
        stype = (r.get("shift_type") or "morning")
        color = _color_for_shift(stype)
        d = r.get("shift_date")

        st = r.get("start_time") or "08:00:00"
        et = r.get("end_time") or "16:00:00"

        events.append({
            "id": str(r.get("id")),
            "title": str(stype).upper(),
            "start": f"{d}T{str(st)[:8]}",
            "end": f"{d}T{str(et)[:8]}",
            "backgroundColor": color,
            "borderColor": color,
            "extendedProps": {
                "shift_type": stype,
                "status": r.get("status") or "scheduled",
                "note": r.get("note") or "",
                "location": r.get("location") or "",
            },
        })

    return jsonify(events)


@app.post("/doctor/api/duty-create", endpoint="doctor_duty_create")
def doctor_duty_create():
    if not require_role("doctor"):
        return jsonify({"ok": False, "msg": "Unauthorized"}), 401

    doctor_id = int(session.get("doctor_id") or 0)
    shift_date = (request.form.get("shift_date") or "").strip()

    ui_shift = (request.form.get("shift_type") or "").strip().lower()
    ui_shift_norm = ui_shift.replace(" ", "").replace("-", "").replace("_", "")

    SHIFT_MAP = {
        "day": "morning",
        "morning": "morning",
        "evening": "afternoon",
        "afternoon": "afternoon",
        "night": "night",
        "oncall": "on_call",
        "oncalll": "on_call",
        "on_call": "on_call",
    }
    shift_type = SHIFT_MAP.get(ui_shift_norm)

    start_time = (request.form.get("start_time") or "08:00").strip()
    end_time = (request.form.get("end_time") or "16:00").strip()
    location = (request.form.get("location") or "").strip()

    if not shift_date or not shift_type:
        return jsonify({"ok": False, "msg": "ข้อมูลไม่ครบ/ประเภทเวรไม่ถูกต้อง"}), 400

    try:
        sd = datetime.strptime(shift_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "msg": "รูปแบบวันที่ไม่ถูกต้อง"}), 400

    if len(start_time) == 5:
        start_time += ":00"
    if len(end_time) == 5:
        end_time += ":00"

    conn = get_db_connection()
    if not conn:
        return jsonify({"ok": False, "msg": "เชื่อมต่อฐานข้อมูลไม่สำเร็จ"}), 500

    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT id
            FROM doctor_shifts
            WHERE doctor_user_id=%s AND shift_date=%s AND shift_type=%s
            LIMIT 1
        """, (doctor_id, sd, shift_type))
        if cur.fetchone():
            return jsonify({"ok": False, "msg": "มีเวรกะนี้ในวันดังกล่าวแล้ว"}), 409

        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO doctor_shifts
              (doctor_user_id, shift_date, shift_type, start_time, end_time, status, note, location)
            VALUES
              (%s,%s,%s,%s,%s,'scheduled','',%s)
        """, (doctor_id, sd, shift_type, start_time, end_time, location or None))
        new_id = cur2.lastrowid
        conn.commit()
        cur2.close()

        log_audit(doctor_id, "CREATE_SHIFT", "doctor_shifts", new_id)

        color = _color_for_shift(shift_type)

        TITLE_MAP = {
            "morning": "DAY",
            "afternoon": "EVENING",
            "night": "NIGHT",
            "on_call": "ON-CALL",
        }

        event = {
            "id": str(new_id),
            "title": TITLE_MAP.get(shift_type, str(shift_type).upper()),
            "start": f"{sd}T{start_time[:8]}",
            "end": f"{sd}T{end_time[:8]}",
            "backgroundColor": color,
            "borderColor": color,
            "extendedProps": {
                "shift_type": shift_type,
                "status": "scheduled",
                "note": "",
                "location": location or "",
            },
        }
        return jsonify({"ok": True, "event": event})

    except Exception as e:
        conn.rollback()
        print("Error duty-create:", e)
        return jsonify({"ok": False, "msg": "บันทึกไม่สำเร็จ"}), 500
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


@app.post("/doctor/api/duty-note-save", endpoint="doctor_duty_note_save")
def doctor_duty_note_save():
    if not require_role("doctor"):
        return jsonify({"ok": False, "msg": "Unauthorized"}), 401

    doctor_id = int(session.get("doctor_id") or 0)
    shift_id = (request.form.get("shift_id") or "").strip()
    note = (request.form.get("note") or "").strip()

    if not shift_id:
        return jsonify({"ok": False, "msg": "missing shift_id"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"ok": False, "msg": "เชื่อมต่อฐานข้อมูลไม่สำเร็จ"}), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE doctor_shifts
            SET note = %s
            WHERE id = %s AND doctor_user_id = %s
        """, (note, shift_id, doctor_id))
        conn.commit()

        ok = cur.rowcount > 0
        cur.close()

        if ok:
            log_audit(doctor_id, "UPDATE_SHIFT_NOTE", "doctor_shifts", int(shift_id))

        return jsonify({"ok": ok})

    except Exception as e:
        conn.rollback()
        print("Error duty-note-save:", e)
        return jsonify({"ok": False, "msg": "บันทึกไม่สำเร็จ"}), 500
    finally:
        conn.close()


# =========================================================
# View-only assessment partials (MMSE/2Q/TGDS/8Q)
# =========================================================
@app.route("/doctor/patient/<hn>/<gcn>/mmse", methods=["GET"])
def doctor_view_mmse(hn, gcn):
    embed = request.args.get("embed") == "1"
    view_only = True

    conn = get_db_connection()
    if not conn:
        abort(500)

    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT v.id AS visit_id
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE p.hn=%s AND p.gcn=%s
        ORDER BY v.visit_datetime DESC, v.id DESC
        LIMIT 1
    """, (hn, gcn))
    vrow = cur.fetchone() or {}
    visit_id = vrow.get("visit_id")

    mmse = {}
    answers = {}

    if visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_mmse
            WHERE visit_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (visit_id,))
        mmse = cur.fetchone() or {}

        mmse_id = mmse.get("id")
        if mmse_id:
            cur.execute("""
                SELECT *
                FROM assessment_mmse_answers
                WHERE mmse_id=%s
                LIMIT 1
            """, (mmse_id,))
            answers = cur.fetchone() or {}

    cur.close()
    conn.close()

    mmse_detail = {}
    if answers:
        mmse_detail.update(answers)
    mmse_detail.setdefault("mmse_edu", (mmse.get("edu_level") if mmse else None) or "primary")

    tpl = "assess/mmse_form_partial.html" if embed else "assess/mmse_page.html"
    return render_template(
        tpl,
        hn=hn,
        gcn=gcn,
        view_only=view_only,
        mmse=mmse,
        answers=answers,
        mmse_detail=mmse_detail,
    )


@app.route("/doctor/patient/<hn>/<gcn>/twoq", methods=["GET"])
def doctor_view_twoq(hn, gcn):
    embed = request.args.get("embed") == "1"
    view_only = True

    conn = get_db_connection()
    if not conn:
        abort(500)

    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT v.id AS visit_id
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE p.hn=%s AND p.gcn=%s
        ORDER BY v.visit_datetime DESC, v.id DESC
        LIMIT 1
    """, (hn, gcn))
    vrow = cur.fetchone() or {}
    visit_id = vrow.get("visit_id")

    twoq = {}
    if visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_depression_2q
            WHERE visit_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (visit_id,))
        twoq = cur.fetchone() or {}

    cur.close()
    conn.close()

    tpl = "assess/twoq_form_partial.html" if embed else "assess/twoq_page.html"
    return render_template(tpl, hn=hn, gcn=gcn, view_only=view_only, twoq=twoq)


@app.route("/doctor/patient/<hn>/<gcn>/tgds", methods=["GET"])
def doctor_view_tgds(hn, gcn):
    embed = request.args.get("embed") == "1"
    view_only = True

    conn = get_db_connection()
    if not conn:
        abort(500)
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT v.id AS visit_id
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE p.hn=%s AND p.gcn=%s
        ORDER BY v.visit_datetime DESC, v.id DESC
        LIMIT 1
    """, (hn, gcn))
    vrow = cur.fetchone() or {}
    visit_id = vrow.get("visit_id")

    row = {}
    if visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_tgds15
            WHERE visit_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (visit_id,))
        row = cur.fetchone() or {}

    cur.close()
    conn.close()

    tpl = "assess/tgds15_form_partial.html" if embed else "assess/tgds15_page.html"
    return render_template(tpl, hn=hn, gcn=gcn, view_only=view_only, row=row)


@app.route("/doctor/patient/<hn>/<gcn>/8q", methods=["GET"])
def doctor_view_8q(hn, gcn):
    embed = request.args.get("embed") == "1"
    view_only = True

    conn = get_db_connection()
    if not conn:
        abort(500)

    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT v.id AS visit_id
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE p.hn=%s AND p.gcn=%s
        ORDER BY v.visit_datetime DESC, v.id DESC
        LIMIT 1
    """, (hn, gcn))
    vrow = cur.fetchone() or {}
    visit_id = vrow.get("visit_id")

    q8 = {}
    if visit_id:
        cur.execute("""
            SELECT *
            FROM assessment_8q
            WHERE visit_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (visit_id,))
        q8 = cur.fetchone() or {}

    cur.close()
    conn.close()

    tpl = "assess/8q_form_partial.html" if embed else "assess/8q_page.html"
    return render_template(tpl, hn=hn, gcn=gcn, view_only=view_only, q8=q8, q8_detail=q8, row=q8)


# =========================================================
# Run App
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
