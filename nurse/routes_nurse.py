from __future__ import annotations
from datetime import date
from datetime import datetime
from typing import Dict, Optional, Tuple, List
import mysql.connector
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from mysql.connector import Error  # type: ignore
from db.db import get_db_connection
from werkzeug.exceptions import Forbidden

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")


# -------------------------
# Auth guard
# -------------------------
def _require_nurse():
    """
    องค์กรมักแยกเป็น guard function เพื่อใช้ซ้ำ + audit ง่าย
    """
    role = session.get("role")
    user_id = session.get("user_id")
    if not user_id:
        flash("กรุณาเข้าสู่ระบบก่อน", "warning")
        return False
    if role != "nurse":
        # ใช้ 403 จะชัดเจนกว่า redirect เงียบ ๆ ในระบบจริง
        raise Forbidden("You do not have permission to access this resource.")
    return True


# -------------------------
# DB introspection helpers
# -------------------------
def _get_db_name(conn) -> str:
    cur = conn.cursor()
    cur.execute("SELECT DATABASE()")
    dbname = cur.fetchone()[0]
    cur.close()
    return dbname


def _q_ident(name: str) -> str:
    # quote identifier with backticks safely
    return "`" + name.replace("`", "``") + "`"


def _pick_first(cols: set, names: List[str]) -> Optional[str]:
    for n in names:
        if n in cols:
            return n
    return None


def _find_patient_table(conn) -> Tuple[str, str, str, str]:
    """
    หา table คนไข้จาก DB จริง โดยดูว่ามี column hn + gcn (case-insensitive)
    และมี id หรือ patient_id
    คืนค่า: (table, id_col, hn_col, gcn_col)
    """
    dbname = _get_db_name(conn)
    cur = conn.cursor(dictionary=True)

    # candidate tables that contain hn+gcn (case-insensitive)
    cur.execute(
        """
        SELECT c.table_name
        FROM information_schema.columns c
        WHERE c.table_schema = %s
          AND LOWER(c.column_name) IN ('hn','gcn')
        GROUP BY c.table_name
        HAVING SUM(LOWER(c.column_name)='hn') > 0
           AND SUM(LOWER(c.column_name)='gcn') > 0
        """,
        (dbname,),
    )
    candidates = [r["table_name"] for r in cur.fetchall()]
    if not candidates:
        cur.close()
        raise RuntimeError("ไม่พบตารางคนไข้ที่มีคอลัมน์ hn และ gcn ในฐานข้อมูล")

    for t in candidates:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (dbname, t),
        )
        cols = {r["column_name"] for r in cur.fetchall()}
        cols_lower = {c.lower(): c for c in cols}

        id_col = _pick_first(cols, ["id", "patient_id", "patientId", "PATIENT_ID"])
        hn_col = cols_lower.get("hn")
        gcn_col = cols_lower.get("gcn")

        if id_col and hn_col and gcn_col:
            cur.close()
            return t, id_col, hn_col, gcn_col

    cur.close()
    raise RuntimeError("พบตารางที่มี hn/gcn แต่ไม่พบคอลัมน์ id/patient_id")


def _find_encounter_table(conn, patient_table: str) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    หา encounter table ที่มี FK ไป patients (หรือมี patient_id)
    คืนค่า: (enc_table, patient_fk_col, date_col, created_at_col)
    - date_col อาจเป็น encounter_date / visit_date / assess_date / ...
    - created_at_col อาจเป็น created_at / createdAt / ...
    """
    dbname = _get_db_name(conn)
    cur = conn.cursor(dictionary=True)

    # 1) หา table ที่มี column patient_id (case-insensitive)
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema=%s AND LOWER(column_name)='patient_id'
        GROUP BY table_name
        """,
        (dbname,),
    )
    candidates = [r["table_name"] for r in cur.fetchall()]

    # 2) ถ้าไม่เจอ ให้หา table ที่มี FK referenced to patient_table
    if not candidates:
        cur.execute(
            """
            SELECT DISTINCT kcu.table_name
            FROM information_schema.key_column_usage kcu
            WHERE kcu.table_schema=%s
              AND kcu.referenced_table_name=%s
            """,
            (dbname, patient_table),
        )
        candidates = [r["table_name"] for r in cur.fetchall()]

    if not candidates:
        cur.close()
        raise RuntimeError("ไม่พบตาราง encounters ที่เชื่อม FK ไป patients")

    date_name_priority = [
        "encounter_date", "visit_date", "assessment_date", "assess_date",
        "date", "created_date"
    ]
    created_priority = ["created_at", "createdAt", "CREATED_AT"]

    for t in candidates:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (dbname, t),
        )
        rows = cur.fetchall()
        cols = {r["column_name"] for r in rows}
        types = {r["column_name"]: r["data_type"] for r in rows}
        cols_lower = {c.lower(): c for c in cols}

        fk_col = cols_lower.get("patient_id")
        if not fk_col:
            # try FK column by key usage referencing patients
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE table_schema=%s AND table_name=%s AND referenced_table_name=%s
                LIMIT 1
                """,
                (dbname, t, patient_table),
            )
            r = cur.fetchone()
            fk_col = r["column_name"] if r else None

        if not fk_col:
            continue

        date_col = None
        for nm in date_name_priority:
            if nm in cols and types.get(nm) in ("date", "datetime", "timestamp"):
                date_col = nm
                break
        if not date_col:
            # any date-like column containing 'date'
            for c in cols:
                if "date" in c.lower() and types.get(c) in ("date", "datetime", "timestamp"):
                    date_col = c
                    break

        created_col = None
        for nm in created_priority:
            if nm in cols and types.get(nm) in ("datetime", "timestamp", "date"):
                created_col = nm
                break
        if not created_col:
            # any created column
            for c in cols:
                if "created" in c.lower() and types.get(c) in ("datetime", "timestamp", "date"):
                    created_col = c
                    break

        cur.close()
        return t, fk_col, date_col, created_col

    cur.close()
    raise RuntimeError("พบ candidates encounters แต่ไม่เจอคอลัมน์ FK patient_id/FK จริง")


def _find_sessions_table(conn, encounter_table: str) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    หา assessment_sessions table ที่มี encounter_id + created_at (ถ้ามี) + created_by (ถ้ามี)
    คืนค่า: (sess_table, encounter_fk_col, created_at_col, created_by_col)
    """
    dbname = _get_db_name(conn)
    cur = conn.cursor(dictionary=True)

    # Prefer table name 'assessment_sessions' if exists
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema=%s AND table_name='assessment_sessions'
        """,
        (dbname,),
    )
    pref = cur.fetchone()
    candidates = ["assessment_sessions"] if pref else []

    if not candidates:
        # fallback: any table with encounter_id
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema=%s AND LOWER(column_name)='encounter_id'
            GROUP BY table_name
            """,
            (dbname,),
        )
        candidates = [r["table_name"] for r in cur.fetchall()]

    if not candidates:
        cur.close()
        raise RuntimeError("ไม่พบตาราง assessment_sessions หรือ table ที่มี encounter_id")

    for t in candidates:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (dbname, t),
        )
        rows = cur.fetchall()
        cols = {r["column_name"] for r in rows}
        types = {r["column_name"]: r["data_type"] for r in rows}
        cols_lower = {c.lower(): c for c in cols}

        enc_fk = cols_lower.get("encounter_id")
        if not enc_fk:
            continue

        created_at = None
        for c in cols:
            if c.lower() == "created_at" and types.get(c) in ("datetime", "timestamp", "date"):
                created_at = c
                break
        if not created_at:
            for c in cols:
                if "created" in c.lower() and types.get(c) in ("datetime", "timestamp", "date"):
                    created_at = c
                    break

        created_by = None
        for c in cols:
            if c.lower() in ("created_by", "createdby"):
                created_by = c
                break

        cur.close()
        return t, enc_fk, created_at, created_by

    cur.close()
    raise RuntimeError("พบ table มี encounter_id แต่ไม่ผ่านเงื่อนไข sessions")


def _find_headers_table(conn) -> Tuple[str, str, str, Optional[str], Optional[str], Optional[str]]:
    """
    หา cga header table ที่มี encounter_id + session_id
    คืนค่า: (hdr_table, encounter_fk_col, session_fk_col, assessed_by_col, assessed_at_col, created_at_col)
    """
    dbname = _get_db_name(conn)
    cur = conn.cursor(dictionary=True)

    # Prefer 'cga_headers' if exists
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema=%s AND table_name='cga_headers'
        """,
        (dbname,),
    )
    pref = cur.fetchone()
    candidates = ["cga_headers"] if pref else []

    if not candidates:
        # any table containing both encounter_id and session_id
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema=%s AND LOWER(column_name) IN ('encounter_id','session_id')
            GROUP BY table_name
            HAVING SUM(LOWER(column_name)='encounter_id')>0 AND SUM(LOWER(column_name)='session_id')>0
            """,
            (dbname,),
        )
        candidates = [r["table_name"] for r in cur.fetchall()]

    if not candidates:
        cur.close()
        raise RuntimeError("ไม่พบตาราง cga_headers (encounter_id + session_id)")

    for t in candidates:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (dbname, t),
        )
        rows = cur.fetchall()
        cols = {r["column_name"] for r in rows}
        types = {r["column_name"]: r["data_type"] for r in rows}
        cols_lower = {c.lower(): c for c in cols}

        enc_fk = cols_lower.get("encounter_id")
        ses_fk = cols_lower.get("session_id")
        if not enc_fk or not ses_fk:
            continue

        assessed_by = cols_lower.get("assessed_by")
        assessed_at = cols_lower.get("assessed_at")
        created_at = cols_lower.get("created_at")

        # fuzzy
        if not assessed_by:
            for c in cols:
                if "assessed_by" in c.lower() or "assessor" in c.lower():
                    assessed_by = c
                    break
        if not assessed_at:
            for c in cols:
                if "assessed_at" in c.lower():
                    assessed_at = c
                    break
        if not created_at:
            for c in cols:
                if "created" in c.lower() and types.get(c) in ("datetime", "timestamp", "date"):
                    created_at = c
                    break

        cur.close()
        return t, enc_fk, ses_fk, assessed_by, assessed_at, created_at

    cur.close()
    raise RuntimeError("พบ candidates header แต่ไม่ผ่านเงื่อนไข")


# -------------------------
# Routes
# -------------------------
@nurse_bp.route("/assess/new", methods=["GET", "POST"], endpoint="assess_new")
def assess_new():
    if not _require_nurse():
        return redirect(url_for("auth.login"))

    page_errors = []
    form = {"hn": "", "gcn": "", "full_name": ""}

    if request.method == "POST":
        hn = (request.form.get("hn") or "").strip()
        gcn = (request.form.get("gcn") or "").strip()
        full_name = (request.form.get("full_name") or "").strip()

        form = {"hn": hn, "gcn": gcn, "full_name": full_name}

        if not hn:
            page_errors.append("กรุณากรอกเลขที่ผู้ป่วย (HN)")
        if not gcn:
            page_errors.append("กรุณากรอกเลขที่คลินิกผู้สูงอายุ (GCN)")
        if not full_name:
            page_errors.append("กรุณากรอกชื่อ-นามสกุลผู้ป่วย")

        if page_errors:
            return render_template("nurse/assess_new.html", page_errors=page_errors, form=form)

        conn = None
        cur = None
        try:
            conn = get_db_connection()
            if conn is None:
                page_errors.append("ระบบฐานข้อมูลไม่พร้อมใช้งาน")
                return render_template("nurse/assess_new.html", page_errors=page_errors, form=form)

            cur = conn.cursor()

            # ✅ สร้าง “รอบประเมินใหม่” เสมอ (ไม่ lookup)
            # ปรับชื่อคอลัมน์ให้ตรง schema ของคุณ
            cur.execute("""
                INSERT INTO assessment_sessions (hn, gcn, full_name, created_by, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (hn, gcn, full_name, session.get("user_id")))

            conn.commit()
            flash("เริ่มการประเมินสำเร็จ", "success")
            return redirect(url_for("nurse.dashboard"))

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            current_app.logger.exception("assess_new failed: %s", e)
            page_errors.append(f"เกิดข้อผิดพลาด DB: {e}")
            return render_template("nurse/assess_new.html", page_errors=page_errors, form=form)

        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    return render_template("nurse/assess_new.html", page_errors=page_errors, form=form)

@nurse_bp.get("/assess/<int:assess_id>", endpoint="assess_detail")
def assess_detail(assess_id: int):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    return render_template("nurse/assess_detail.html", assess_id=assess_id)

@nurse_bp.post("/assess/create", endpoint="assess_create")
def assess_create():
    if not _require_nurse():
        return redirect(url_for("auth.login"))

    hn = (request.form.get("hn") or "").strip()
    gcn = (request.form.get("gcn") or "").strip()

    if not hn or not gcn:
        flash("กรุณากรอก HN และ GCN ให้ครบ", "danger")
        return redirect(url_for("nurse.assess_new"))

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # =========================
        # 1) หา patient ถ้าไม่เจอ => สร้างใหม่
        # =========================
        cur.execute(
            "SELECT id, hn, gcn FROM patients WHERE hn=%s AND gcn=%s LIMIT 1",
            (hn, gcn),
        )
        patient = cur.fetchone()

        if not patient:
            # ⚠️ ถ้า patients ของคุณมีคอลัมน์บังคับมากกว่านี้ (ชื่อ-สกุล/เพศ/วันเกิด)
            # ให้เพิ่ม field ตรงนี้ตาม schema จริง
            cur.execute(
                """
                INSERT INTO patients (hn, gcn, created_at)
                VALUES (%s, %s, NOW())
                """,
                (hn, gcn),
            )
            patient_id = cur.lastrowid
            flash("สร้างข้อมูลผู้ป่วยใหม่สำเร็จ", "success")
        else:
            patient_id = patient["id"]

        nurse_user_id = session.get("user_id")  # ต้องมีตอน login
        if not nurse_user_id:
            flash("Session หลุด กรุณาเข้าสู่ระบบใหม่", "danger")
            return redirect(url_for("auth.login"))

        # =========================
        # 2) สร้าง encounter (visit)
        # =========================
        cur.execute(
            """
            INSERT INTO encounters (patient_id, created_by, created_at)
            VALUES (%s, %s, NOW())
            """,
            (patient_id, nurse_user_id),
        )
        encounter_id = cur.lastrowid

        # =========================
        # 3) สร้าง assessment header
        # =========================
        cur.execute(
            """
            INSERT INTO assessment_headers (patient_id, encounter_id, created_by, created_at, status)
            VALUES (%s, %s, %s, NOW(), %s)
            """,
            (patient_id, encounter_id, nurse_user_id, "IN_PROGRESS"),
        )
        assess_id = cur.lastrowid

        conn.commit()

        flash("เริ่มการประเมินสำเร็จ", "success")
        return redirect(url_for("nurse.assess_detail", assess_id=assess_id))

    except mysql.connector.Error as e:
        if conn:
            conn.rollback()
        flash(f"เกิดข้อผิดพลาด DB: {e}", "danger")
        return redirect(url_for("nurse.assess_new"))

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"เกิดข้อผิดพลาดระบบ: {e}", "danger")
        return redirect(url_for("nurse.assess_new"))

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@nurse_bp.get("/assess/session/<int:header_id>", endpoint="assess_session")
def assess_session(header_id: int):
    if not _require_nurse():
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "danger")
        return redirect(url_for("nurse.assess_new"))

    cur = conn.cursor(dictionary=True)

    try:
        # ใช้ตาราง header จริง + patients จริง
        patient_table, patient_id_col, hn_col, gcn_col = _find_patient_table(conn)
        hdr_table, hdr_enc_fk, hdr_sess_fk, *_ = _find_headers_table(conn)
        enc_table, enc_patient_fk, *_ = _find_encounter_table(conn, patient_table)

        # join: header -> encounter -> patient
        cur.execute(
            f"""
            SELECT
              h.id AS header_id,
              p.{_q_ident(hn_col)}  AS hn,
              p.{_q_ident(gcn_col)} AS gcn
            FROM {_q_ident(hdr_table)} h
            JOIN {_q_ident(enc_table)} e ON e.id = h.{_q_ident(hdr_enc_fk)}
            JOIN {_q_ident(patient_table)} p ON p.{_q_ident(patient_id_col)} = e.{_q_ident(enc_patient_fk)}
            WHERE h.id = %s
            LIMIT 1
            """,
            (header_id,),
        )
        assess = cur.fetchone()
        if not assess:
            flash("ไม่พบข้อมูลการประเมิน", "warning")
            return redirect(url_for("nurse.assess_new"))

        return render_template(
            "nurse/assess_session.html",
            assess=assess,
            hn=assess["hn"],
            gcn=assess["gcn"],
            header_id=header_id,
        )

    finally:
        cur.close()
        conn.close()

@nurse_bp.get("/dashboard", endpoint="dashboard")
def dashboard():
    # ===== Auth / RBAC (องค์กรนิยมเช็ค user_id ด้วย) =====
    if not session.get("user_id"):
        flash("กรุณาเข้าสู่ระบบก่อน", "warning")
        return redirect(url_for("auth.login"))

    if session.get("role") != "nurse":
        flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้", "danger")
        return redirect(url_for("auth.login"))

    conn = None
    cur = None

    # default KPI กันหน้าแตก
    kpis = {"today": 0, "week": 0, "month": 0, "total": 0}

    try:
        conn = get_db_connection()
        if conn is None:
            flash("ระบบฐานข้อมูลไม่พร้อมใช้งาน", "danger")
            return render_template(
                "nurse/dashboard.html",
                kpis=kpis,
                user=session.get("username") or session.get("user") or "-",
                role="พยาบาล",
            )

        cur = conn.cursor(dictionary=True)

        # ===== KPI (มาตรฐาน: ใช้ช่วงเวลาแบบ explicit) =====
        # today
        cur.execute("""
            SELECT COUNT(*) AS c
            FROM assessment_sessions
            WHERE created_at >= CURDATE()
              AND created_at <  CURDATE() + INTERVAL 1 DAY
        """)
        kpis["today"] = int(cur.fetchone()["c"] or 0)

        # week (ISO week: monday-first)
        cur.execute("""
            SELECT COUNT(*) AS c
            FROM assessment_sessions
            WHERE YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)
        """)
        kpis["week"] = int(cur.fetchone()["c"] or 0)

        # month
        cur.execute("""
            SELECT COUNT(*) AS c
            FROM assessment_sessions
            WHERE created_at >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
              AND created_at <  DATE_FORMAT(CURDATE() + INTERVAL 1 MONTH, '%Y-%m-01')
        """)
        kpis["month"] = int(cur.fetchone()["c"] or 0)

        # total
        cur.execute("SELECT COUNT(*) AS c FROM assessment_sessions")
        kpis["total"] = int(cur.fetchone()["c"] or 0)

    except Error as e:
        current_app.logger.exception("Nurse dashboard KPI query failed: %s", e)
        flash("เกิดข้อผิดพลาดในการโหลดสถิติ Dashboard", "danger")

    except Exception as e:
        current_app.logger.exception("Nurse dashboard failed: %s", e)
        flash("เกิดข้อผิดพลาดของระบบ", "danger")

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return render_template(
        "nurse/dashboard.html",
        kpis=kpis,
        user=session.get("username") or session.get("user") or "-",
        role="พยาบาล",
    )


@nurse_bp.get("/patients", endpoint="patients")
def patients():
    # ===== Auth / RBAC =====
    if not _require_nurse():
        return redirect(url_for("auth.login"))

    # ===== Query params (search + pagination) =====
    q = (request.args.get("q") or "").strip()
    page_str = (request.args.get("page") or "1").strip()
    size_str = (request.args.get("page_size") or "20").strip()

    try:
        page = max(int(page_str), 1)
    except ValueError:
        page = 1

    try:
        page_size = int(size_str)
        if page_size not in (10, 20, 50, 100):
            page_size = 20
    except ValueError:
        page_size = 20

    offset = (page - 1) * page_size

    # ===== DB fetch =====
    conn = None
    cur = None
    rows = []
    total = 0

    try:
        conn = get_db_connection()
        if conn is None:
            current_app.logger.error("DB connection is None")
            flash("ระบบฐานข้อมูลไม่พร้อมใช้งาน (DB connection failed)", "danger")
            return render_template(
                "nurse/patients.html",
                patients=[],
                q=q,
                page=page,
                page_size=page_size,
                total=0,
                total_pages=0,
            )

        cur = conn.cursor(dictionary=True)

        # หมายเหตุ: ชื่อตาราง/คอลัมน์อาจต่างกันตาม schema ทีมคุณ
        # ตัวอย่างนี้ใช้ตาราง `patients` และฟิลด์ทั่วไป: hn, first_name, last_name, phone, updated_at
        where_sql = ""
        params = {}

        if q:
            where_sql = """
                WHERE
                    p.hn LIKE %(kw)s OR
                    p.first_name LIKE %(kw)s OR
                    p.last_name LIKE %(kw)s OR
                    CONCAT(p.first_name, ' ', p.last_name) LIKE %(kw)s
            """
            params["kw"] = f"%{q}%"

        # นับจำนวนทั้งหมดเพื่อทำ pagination
        cur.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM patients p
            {where_sql}
            """,
            params,
        )
        total = int(cur.fetchone()["cnt"])

        # ดึงรายการหน้า current page
        params2 = dict(params)
        params2.update({"limit": page_size, "offset": offset})

        cur.execute(
            f"""
            SELECT
                p.id,
                p.hn,
                p.first_name,
                p.last_name,
                p.gender,
                p.birth_date,
                p.phone,
                p.updated_at
            FROM patients p
            {where_sql}
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params2,
        )
        rows = cur.fetchall() or []

        total_pages = (total + page_size - 1) // page_size

        return render_template(
            "nurse/patients.html",
            patients=rows,
            q=q,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )

    except Forbidden:
        # แสดงหน้า 403 หรือ redirect ก็ได้ แต่ในองค์กรนิยมให้ชัดเจน
        flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้", "danger")
        return redirect(url_for("auth.login"))

    except Exception as e:
        current_app.logger.exception("patients() failed: %s", e)
        flash("เกิดข้อผิดพลาดในการโหลดรายชื่อผู้ป่วย", "danger")
        return render_template(
            "nurse/patients.html",
            patients=[],
            q=q,
            page=page,
            page_size=page_size,
            total=0,
            total_pages=0,
        )

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

@nurse_bp.route("/patients/new", methods=["GET", "POST"], endpoint="add_patient")
def add_patient():
    if not session.get("user_id") or session.get("role") != "nurse":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        hn = (request.form.get("hn") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None

        # validate แบบองค์กร (ขั้นต่ำ)
        if not hn or not first_name or not last_name:
            flash("กรุณากรอก HN, ชื่อ และนามสกุลให้ครบ", "warning")
            return render_template("nurse/patient_form.html", form=request.form)

        conn = None
        cur = None
        try:
            conn = get_db_connection()
            if conn is None:
                flash("ระบบฐานข้อมูลไม่พร้อมใช้งาน", "danger")
                return render_template("nurse/patient_form.html", form=request.form)

            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO patients (hn, first_name, last_name, phone, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """,
                (hn, first_name, last_name, phone),
            )
            conn.commit()
            flash("เพิ่มผู้ป่วยสำเร็จ", "success")
            return redirect(url_for("nurse.patients"))

        except Exception as e:
            if conn:
                conn.rollback()
            current_app.logger.exception("add_patient failed: %s", e)
            flash("เพิ่มผู้ป่วยไม่สำเร็จ", "danger")
            return render_template("nurse/patient_form.html", form=request.form)

        finally:
            try:
                if cur:
                    cur.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    # GET
    return render_template("nurse/patient_form.html", form={})