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

    kpis = {"today": 0, "month": 0, "year": 0, "total": 0}

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return render_template("nurse/dashboard.html", kpis=kpis)

    try:
        cur = conn.cursor(dictionary=True)

        # total patients
        cur.execute("SELECT COUNT(*) AS c FROM patients")
        kpis["total"] = (cur.fetchone() or {}).get("c", 0) or 0

        # --- detect datetime column in encounters ---
        cur.execute("""
            SELECT COLUMN_NAME AS c
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'encounters'
        """)
        cols = {r["c"] for r in (cur.fetchall() or []) if r.get("c")}

        dt_col = _first_existing(cols, [
            "encounter_datetime",
            "visit_datetime",
            "encounter_date",
            "created_at",
            "updated_at",
        ])

        if not dt_col:
            # ไม่มีคอลัมน์เวลาเลย ก็โชว์ 0 ไปก่อน ไม่ให้พัง
            return render_template("nurse/dashboard.html", kpis=kpis)

        # today
        cur.execute(
            f"SELECT COUNT(DISTINCT patient_id) AS c FROM encounters WHERE DATE({dt_col}) = CURDATE()"
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

        return render_template("nurse/dashboard.html", kpis=kpis)

    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

@nurse_bp.get("/assess/start", endpoint="assess_start")
def assess_start():
    if session.get("role") != "nurse":
        return redirect(url_for("auth.login"))
    return render_template("nurse/assess_start.html")  # หรือจะ redirect ไปหน้าที่มีอยู่
