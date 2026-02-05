from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db.db import get_db_connection

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

from flask import Blueprint, render_template, redirect, url_for, session

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

@nurse_bp.get("/")
def index():
    if session.get("role") == "nurse" and session.get("user_id"):
        return redirect(url_for("nurse.dashboard"))
    return redirect(url_for("auth.login"))

def _first_existing(colset: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colset:
            return c
    return None

@nurse_bp.get("/dashboard")
def dashboard():
    if session.get("role") != "nurse":
        return redirect(url_for("auth.login"))

    # =========================================================
    # ✅ Default data (องค์กร: template ต้องไม่เจอ Undefined)
    # =========================================================
    kpis = {"today": 0, "week": 0, "month": 0, "year": 0, "total": 0}

    # ✅ ตัวแปรที่ dashboard.html ใช้ tojson (ต้องมีเสมอ)
    bar_labels: list[str] = []
    bar_values: list[int] = []
    risk = []  # จะใช้เป็น list/dict ก็ได้ ตอนนี้กันพังไว้ก่อน

    # helper ให้ return ทุกกรณีส่ง data ครบ
    def _render():
        return render_template(
            "nurse/dashboard.html",
            kpis=kpis,
            bar_labels=bar_labels,
            bar_values=bar_values,
            risk=risk,
        )

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return _render()

    cur = None
    try:
        cur = conn.cursor(dictionary=True)

        # total patients
        cur.execute("SELECT COUNT(*) AS c FROM patients")
        kpis["total"] = (cur.fetchone() or {}).get("c", 0) or 0

        # --- detect datetime column in encounters ---
        cur.execute(
            """
            SELECT COLUMN_NAME AS c
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'encounters'
            """
        )
        cols = {r["c"] for r in (cur.fetchall() or []) if r.get("c")}

        dt_col = _first_existing(
            cols,
            [
                "encounter_datetime",
                "visit_datetime",
                "encounter_date",
                "created_at",
                "updated_at",
            ],
        )

        if dt_col:
            # today
            cur.execute(
                f"SELECT COUNT(DISTINCT patient_id) AS c "
                f"FROM encounters WHERE DATE({dt_col}) = CURDATE()"
            )
            kpis["today"] = (cur.fetchone() or {}).get("c", 0) or 0
    
            # month
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE YEAR({dt_col})=YEAR(CURDATE())
                  AND MONTH({dt_col})=MONTH(CURDATE())
                """
            )
            kpis["month"] = (cur.fetchone() or {}).get("c", 0) or 0

            # year
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT patient_id) AS c
                FROM encounters
                WHERE YEAR({dt_col})=YEAR(CURDATE())
                """
            )
            kpis["year"] = (cur.fetchone() or {}).get("c", 0) or 0
        # ถ้าไม่เจอ dt_col ก็ปล่อย KPI เป็น 0 (ไม่พัง)

        # =========================================================
        # ✅ Data สำหรับกราฟ (ให้ตรงกับ template)
        # =========================================================
        bar_labels = ["Today", "Month", "Year", "Total"]
        bar_values = [kpis["today"], kpis["month"], kpis["year"], kpis["total"]]

        # risk: ตอนนี้ยังไม่ทำจริงก็ส่ง default ไปก่อน
        # ตัวอย่าง format ที่ใช้ได้:
        # risk = [{"label": "high", "count": 0}, {"label": "medium", "count": 0}, {"label": "low", "count": 0}]
        risk = []

        return _render()

    except Exception as e:
        print("❌ nurse.dashboard error:", e)
        flash("โหลดข้อมูล Dashboard ไม่สำเร็จ", "error")
        return _render()

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

@nurse_bp.get("/assess/start", endpoint="assess_start")
def assess_start():
    if session.get("role") != "nurse":
        return redirect(url_for("auth.login"))
    return render_template("nurse/assess_start.html")  # หรือจะ redirect ไปหน้าที่มีอยู่

@nurse_bp.route("/patients", endpoint="patient_list")
def patient_list():
    return render_template("nurse/patients.html")  # หรือชื่อไฟล์ที่คุณมีจริง
