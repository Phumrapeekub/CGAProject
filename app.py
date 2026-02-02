from datetime import datetime, date, timedelta
from flask import request, render_template
import mysql.connector
from mysql.connector import Error
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from ai_multi_models import predict_all



TH_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน",
    "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
    "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
]

def format_th_date(d: date) -> str:
    return f"{d.day} {TH_MONTHS[d.month]} {d.year + 543}"

def format_th_month(d: date) -> str:
    return f"{TH_MONTHS[d.month]} {d.year + 543}"

def get_week_range(d: date):
    start = d - timedelta(days=d.weekday())   # จันทร์
    end = start + timedelta(days=6)           # อาทิตย์
    return start, end


def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",       # หรือ "127.0.0.1"
            user="root",            # 👈 ชื่อผู้ใช้ MySQL ของคุณ
            password="Kantiya203_",            # 👈 ถ้ามีรหัสผ่านให้ใส่ที่นี่
            database="cga_system",   # 👈 ชื่อ database ที่คุณสร้างใน MySQL Workbench
            autocommit=False
        )
        print("✅ Database connected successfully")
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Database connection error: {err}")
        return None
    
def _get_latest_session(conn, patient_id: int, form_code: str):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT * FROM assessment_sessions
        WHERE patient_id=%s AND form_code=%s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """, (patient_id, form_code))
    row = cur.fetchone()
    cur.close()
    return row

def _get_answers(conn, session_id: int):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT question_code, answer_value
        FROM assessment_answers
        WHERE session_id=%s
    """, (session_id,))
    rows = cur.fetchall()
    cur.close()
    return {r["question_code"]: (r["answer_value"] or "") for r in rows}

def _compute_mmse(answers: dict) -> int:
    total = 0
    for i in range(1, 31):
        v = answers.get(f"Q{i}", "0")
        try:
            total += int(v)
        except:
            total += 0
    return total

def save_log(user, action, hn=None, gcn=None, detail=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audit_logs (user, action, hn, gcn, detail)
        VALUES (%s, %s, %s, %s, %s)
    """, (user, action, hn, gcn, detail))
    conn.commit()
    cur.close()
    conn.close()

def redirect_back(default_endpoint="patient_list", **kwargs):
    """กลับไปหน้าก่อนหน้า (referrer) ถ้ามี ไม่งั้นไป endpoint ที่กำหนด"""
    ref = request.referrer
    if ref:
        return redirect(ref)
    return redirect(url_for(default_endpoint, **kwargs))


def get_patient_id_by_hn_gcn(hn, gcn):
    conn = get_db_connection()
    if not conn:
        return None

    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id FROM patient_history WHERE hn = %s AND gcn = %s ORDER BY id DESC LIMIT 1",
        (hn, gcn)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return row["id"] if row else None

def convert_hearing(value):
    """แปลงข้อมูลการได้ยินให้เป็นตัวเลขตามเกณฑ์ที่ใช้ตอน train"""
    if isinstance(value, str):
        value = value.strip()

        if "ปกติ" in value:
            return 0
        if "ติ๊กติ๊ก" in value:
            return 1
        if "ไม่ได้ยิน" in value:
            return 2

        return 1  # ค่า default เมื่อข้อมูลไม่ชัดเจน

    return 0 if value is None else value


def convert_vision(value):
    """แปลงค่า Snellen เช่น 20/20 → 1.0, 20/40 → 0.5"""
    if isinstance(value, str):
        value = value.strip()
        if "/" in value:
            try:
                top, bottom = value.split("/")
                return float(top) / float(bottom)
            except:
                return 1.0  # default มองเห็นปกติ
        return 1.0

    return 1.0 if value is None else value

# =========================
# CGA Answer → Label mapping
# =========================
def map_answers(row: dict, question_map: dict):
    """
    row: dict จาก cursor(dictionary=True) เช่น mmse_detail
    question_map: dict {"q1_1": "คำถาม...", ...}
    คืนค่าเป็น list ของ dict [{key, label, value}, ...]
    """
    if not row:
        return []
    items = []
    for k, label in question_map.items():
        if k in row:
            items.append({
                "key": k,
                "label": label,
                "value": row.get(k)
            })
    return items


# ---------- TGDS-15 (ใช่/ไม่ใช่) ----------
TGDS_QUESTIONS = {
    "q1": "พอใจในชีวิตของตนเองหรือไม่",
    "q2": "ลดกิจกรรมและความสนใจลงหรือไม่",
    "q3": "รู้สึกชีวิตว่างเปล่าหรือไม่",
    "q4": "รู้สึกเบื่อบ่อยหรือไม่",
    "q5": "มีความหวังต่ออนาคตหรือไม่",
    "q6": "มีเรื่องรบกวนใจบ่อยหรือไม่",
    "q7": "อารมณ์โดยรวมส่วนใหญ่รู้สึกเป็นสุขหรือไม่",
    "q8": "รู้สึกกลัวว่าจะมีเรื่องไม่ดีเกิดขึ้นหรือไม่",
    "q9": "รู้สึกมีความสุขส่วนใหญ่ของเวลาหรือไม่",
    "q10": "รู้สึกหมดหนทาง/ช่วยตัวเองไม่ได้หรือไม่",
    "q11": "กระสับกระส่าย/กังวลมากกว่าปกติหรือไม่",
    "q12": "ชอบอยู่บ้านมากกว่าออกไปทำอะไรข้างนอกหรือไม่",
    "q13": "กังวลว่าอนาคตจะไม่ดีหรือไม่",
    "q14": "รู้สึกมีปัญหาด้านความจำมากขึ้นหรือไม่",
    "q15": "คิดว่าการมีชีวิตอยู่เป็นเรื่องดีหรือไม่",
}

# ---------- 8Q / SRA ----------
SRA_QUESTIONS = {
    "q1": "ใน 1 เดือนที่ผ่านมา มีความคิดอยากตายหรือไม่",
    "q2": "ใน 1 เดือนที่ผ่านมา อยากทำร้ายตนเองหรือไม่",
    "q3": "ใน 1 เดือนที่ผ่านมา เคยคิดแผนการฆ่าตัวตายหรือไม่",
    "q4": "ใน 1 เดือนที่ผ่านมา เคยเตรียมการเพื่อฆ่าตัวตายหรือไม่",
    "q5": "ใน 1 เดือนที่ผ่านมา เคยพยายามฆ่าตัวตายหรือไม่",
    "q6": "มีประวัติพยายามฆ่าตัวตายในอดีตหรือไม่",
    "q7": "มีโรค/ภาวะทางจิตเวช หรือใช้สารเสพติดร่วมด้วยหรือไม่",
    "q8": "มีเหตุการณ์กระทบกระเทือนจิตใจ/ความเครียดรุนแรงหรือไม่",
}

# ---------- MMSE-T (ทำเป็น label ใช้งานจริงแบบอ่านออก) ----------
MMSE_QUESTIONS = {
    # Orientation to time (5)
    "q1_1": "บอกปีปัจจุบันได้",
    "q1_2": "บอกฤดูกาล/ช่วงเวลาได้",
    "q1_3": "บอกเดือนปัจจุบันได้",
    "q1_4": "บอกวันที่ได้",
    "q1_5": "บอกวันในสัปดาห์ได้",

    # Orientation to place (5)
    "q2_1": "บอกสถานที่/สถานพยาบาลที่อยู่ได้",
    "q2_2": "บอกชั้น/ห้อง/บริเวณได้",
    "q2_3": "บอกอำเภอ/เขตได้",
    "q2_4": "บอกจังหวัดได้",
    "q2_5": "บอกประเทศได้",

    # Registration (3)
    "q3": "จำคำ 3 คำได้ (การบอกคำแล้วให้ทวน)",

    # Attention/Calculation (5) บางที่แยกเป็น 2 ช่อง
    "q4_1": "ลบเลขต่อเนื่อง/คำนวณ (ส่วนที่ 1)",
    "q4_2": "ลบเลขต่อเนื่อง/คำนวณ (ส่วนที่ 2)",

    # Recall (3)
    "q5": "จำคำเดิม 3 คำได้ (การทดสอบจำย้อนหลัง)",

    # Language & Praxis
    "q6": "การตั้งชื่อวัตถุ 2 อย่าง",
    "q7": "พูดตามประโยคที่กำหนด",
    "q8": "ทำตามคำสั่ง 3 ขั้นตอน",
    "q9": "อ่านแล้วทำตามคำสั่ง",
    "q10": "เขียนประโยคได้",
    "q11": "คัดลอกภาพ/วาดรูปได้",
}


# -------------------------
# ฟังก์ชันดึงข้อมูลสำหรับ AI
# -------------------------

def get_ai_features_from_db(hn, gcn):
    """
    ดึงข้อมูลล่าสุดของผู้ป่วย แล้วแปลงเป็นชุดตัวเลขสำหรับ AI predict_all()
    """
    conn = get_db_connection()
    if not conn:
        print("❌ DB error: cannot connect")
        return None

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT *
        FROM patient_history
        WHERE hn = %s AND gcn = %s
        ORDER BY id DESC
        LIMIT 1
    """, (hn, gcn))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        print("❌ No patient_history found for AI")
        return None

    # -------------------------
    # เตรียมค่า (เผื่อ None ให้เป็น 0)
    # -------------------------
    age  = row.get("age")  or 0
    mmse = row.get("mmse") or 0
    tgds = row.get("tgds") or 0
    q8   = row.get("sra")  or 0   # ใช้คะแนน SRA รวมแทน 8Q

    # ค่าการได้ยินและการมองเห็น
    hl_raw = row.get("hearing_left")
    hr_raw = row.get("hearing_right")
    vs_raw = row.get("vision_snellen")  # ระบบมีช่องเดียว → ใช้ทั้ง 2 ข้าง

    # แปลงให้เป็นตัวเลข
    hl = convert_hearing(hl_raw)
    hr = convert_hearing(hr_raw)
    vr = convert_vision(vs_raw)
    vl = convert_vision(vs_raw)

    # -------------------------
    # ฟังก์ชันกัน None → float
    # -------------------------
    def safe_float(x, default=0.0):
        try:
            if x is None:
                return default
            return float(x)
        except:
            return default

    # -------------------------
    # คืนค่าที่พร้อมส่งเข้า AI
    # -------------------------
    return {
        "patient_id": row["id"],
        "name": row.get("name") or "ไม่ระบุชื่อ",
        "age": int(age),
        "mmse_score": safe_float(mmse),
        "tgds_score": safe_float(tgds),
        "q8_score":   safe_float(q8),
        "hl_score":   safe_float(hl),
        "hr_score":   safe_float(hr),
        "vr_score":   safe_float(vr),
        "vl_score":   safe_float(vl),
    }

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # ใช้กับ flash และ session

FORM_SPECS = {
    "MMSE": {"title": "แก้ไข MMSE ล่าสุด", "questions": [f"Q{i}" for i in range(1, 31)]},
    "TGDS": {"title": "แก้ไข TGDS-15 ล่าสุด", "questions": [f"Q{i}" for i in range(1, 16)]},
    "8Q":   {"title": "แก้ไข 8Q ล่าสุด", "questions": [f"Q{i}" for i in range(1, 9)]},
    "SRA":  {"title": "แก้ไข SRA ล่าสุด", "questions": [f"Q{i}" for i in range(1, 24)]},  # ปรับจำนวนตามจริง
    # เพิ่มแบบอื่น ๆ ได้เรื่อย ๆ
}

@app.get("/patients/<int:patient_id>/forms/<form_code>/edit")
def form_edit(patient_id, form_code):
    form_code = (form_code or "").upper()
    spec = FORM_SPECS.get(form_code)
    if not spec:
        abort(404)

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("patient_list"))

    base = _get_latest_session(conn, patient_id, form_code)
    answers = _get_answers(conn, base["id"]) if base else {}
    conn.close()

    return render_template(
        "form_edit_generic.html",
        patient_id=patient_id,
        form_code=form_code,
        spec=spec,
        base=base,
        answers=answers,
    )

@app.post("/patients/<int:patient_id>/forms/<form_code>/edit")
def form_edit_save(patient_id, form_code):
    form_code = (form_code or "").upper()
    spec = FORM_SPECS.get(form_code)
    if not spec:
        abort(404)

    reason = (request.form.get("reason") or "").strip()
    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("form_edit", patient_id=patient_id, form_code=form_code))

    cur = conn.cursor(dictionary=True)
    try:
        base = _get_latest_session(conn, patient_id, form_code)
        if not base:
            flash(f"ยังไม่มี {form_code} ให้แก้ไข", "error")
            return redirect(url_for("form_edit", patient_id=patient_id, form_code=form_code))

        base_id = base["id"]
        user_id = session.get("user_id")

        # 1) สร้าง session ใหม่
        cur.execute("""
            INSERT INTO assessment_sessions (patient_id, form_code, status, created_by_user_id, note)
            VALUES (%s,%s,'corrected',%s,%s)
        """, (patient_id, form_code, user_id, reason or None))
        new_id = cur.lastrowid

        # 2) copy answers เดิมมาไว้ก่อน
        cur.execute("""
            INSERT INTO assessment_answers (session_id, question_code, answer_value, answer_json)
            SELECT %s, question_code, answer_value, answer_json
            FROM assessment_answers
            WHERE session_id=%s
        """, (new_id, base_id))

        # 3) upsert answers ใหม่ตามข้อที่กำหนด
        for q in spec["questions"]:
            val = request.form.get(q)
            if val is None:
                continue
            cur.execute("""
                INSERT INTO assessment_answers (session_id, question_code, answer_value)
                VALUES (%s,%s,%s)
                ON DUPLICATE KEY UPDATE answer_value=VALUES(answer_value)
            """, (new_id, q, val))

        # 4) compute score (แต่ละแบบคำนวณไม่เหมือนกัน)
        cur.execute("SELECT question_code, answer_value FROM assessment_answers WHERE session_id=%s", (new_id,))
        rows = cur.fetchall()
        ans = {r["question_code"]: (r["answer_value"] or "0") for r in rows}

        total = compute_form_score(form_code, ans)  # ✅ ทำฟังก์ชันนี้ด้านล่าง

        cur.execute("INSERT INTO assessment_scores (session_id, total_score) VALUES (%s,%s)", (new_id, total))

        # 5) revision log
        cur.execute("""
            INSERT INTO assessment_revisions (patient_id, form_code, base_session_id, new_session_id,
                                              corrected_by_user_id, reason)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (patient_id, form_code, base_id, new_id, user_id, reason or None))

        conn.commit()
        flash(f"บันทึกการแก้ไข {form_code} เรียบร้อย", "success")
        return redirect(url_for("form_edit", patient_id=patient_id, form_code=form_code))

    except Exception as e:
        conn.rollback()
        flash(f"บันทึกไม่สำเร็จ: {e}", "error")
        return redirect(url_for("form_edit", patient_id=patient_id, form_code=form_code))
    finally:
        cur.close()
        conn.close()

def compute_form_score(form_code: str, answers: dict) -> int:
    form_code = (form_code or "").upper()

    if form_code == "MMSE":
        total = 0
        for i in range(1, 31):
            total += int(answers.get(f"Q{i}", "0") or 0)
        return total

    if form_code == "TGDS":
        # TGDS-15 โดยทั่วไป: Yes/No ให้คะแนนบางข้อ (มี reverse ได้)
        # ตอนนี้ใช้แบบรวม 0/1 ไปก่อนให้ไม่พัง แล้วค่อยใส่ reverse mapping ทีหลัง
        total = 0
        for i in range(1, 16):
            total += int(answers.get(f"Q{i}", "0") or 0)
        return total

    if form_code == "8Q":
        total = 0
        for i in range(1, 9):
            total += int(answers.get(f"Q{i}", "0") or 0)
        return total

    if form_code == "SRA":
        total = 0
        for k, v in answers.items():
            if k.startswith("Q"):
                total += int(v or 0)
        return total

    # default
    return 0


# ------------------- หน้าเข้าสู่ระบบ -------------------
@app.get("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not username or not password:
            flash("กรุณากรอกชื่อผู้ใช้งานและรหัสผ่านให้ครบถ้วน", "error")
            return render_template("login.html", username=username)

        # ✅ ตัวอย่างล็อกอิน (ยังไม่เชื่อม DB)
        if username == "nurse" and password == "1234":
            session["user"] = "พยาบาลCCS"
            session["role"] = "พยาบาล"
            return redirect(url_for("dashboard"))
        else:
            flash("ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง", "error")
            return render_template("login.html", username=username)

    return render_template("login.html")


# ------------------- ออกจากระบบ -------------------
@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------- หน้าเริ่มประเมินผู้ป่วยใหม่ -------------------
@app.route("/assess/new", methods=["GET", "POST"], endpoint="assess_start")
def assess_new():
    
    if request.method == "POST":
        hn  = (request.form.get("hn") or "").strip()
        gcn = (request.form.get("gcn") or "").strip()

        if not hn or not gcn:
            flash("กรุณากรอก HN และ GCN ให้ครบถ้วน", "error")
            return render_template("assess_new.html", hn=hn, gcn=gcn)

        # ✅ ตอนนี้ยังไม่เชื่อม DB — แค่พาไปหน้าถัดไปจำลอง
        return redirect(url_for("assess_session", hn=hn, gcn=gcn))

    return render_template("assess_new.html")


# ------------------- หน้าฟอร์มการประเมิน -------------------

# STEP 2: MMSE (ตามภาพ)
@app.route("/assess/<hn>/<gcn>/mmse", methods=["GET", "POST"])
def mmse_next(hn, gcn):
    # หา patient_id จาก hn/gcn
    patient_id = get_patient_id_by_hn_gcn(hn, gcn)

    if not patient_id:
        flash("ยังไม่มีข้อมูลขั้นตอนที่ 1 สำหรับ HN/GCN นี้", "error")
        return redirect(url_for("assess_session", hn=hn, gcn=gcn))

    # ========== POST: กดบันทึก MMSE (ไม่ว่าจะกดปุ่มไหน) ==========
    if request.method == "POST":

        def gi(name):
            """แปลงค่าจากฟอร์มเป็น int ถ้าไม่มีให้เป็น 0"""
            try:
                return int(request.form.get(name, 0) or 0)
            except ValueError:
                return 0

        edu = request.form.get("edu") or None
        mmse_total = gi("total_score")

        # q1–q11
        q1_1 = gi("q1_1"); q1_2 = gi("q1_2"); q1_3 = gi("q1_3"); q1_4 = gi("q1_4"); q1_5 = gi("q1_5")
        q2_1 = gi("q2_1"); q2_2 = gi("q2_2"); q2_3 = gi("q2_3"); q2_4 = gi("q2_4"); q2_5 = gi("q2_5")
        q3   = gi("q3")
        q4_1 = gi("q4_1"); q4_2 = gi("q4_2")
        q5   = gi("q5");   q6   = gi("q6");   q7   = gi("q7")
        q8   = gi("q8");   q9   = gi("q9");   q10  = gi("q10"); q11 = gi("q11")

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # ดูว่ามี MMSE เดิมแล้วหรือยัง
        cur.execute("SELECT id FROM assessment_mmse WHERE patient_id = %s", (patient_id,))
        row = cur.fetchone()

        if row:
            # UPDATE
            cur.execute("""
                UPDATE assessment_mmse
                SET edu=%s,
                    q1_1=%s, q1_2=%s, q1_3=%s, q1_4=%s, q1_5=%s,
                    q2_1=%s, q2_2=%s, q2_3=%s, q2_4=%s, q2_5=%s,
                    q3=%s,
                    q4_1=%s, q4_2=%s,
                    q5=%s, q6=%s, q7=%s, q8=%s,
                    q9=%s, q10=%s, q11=%s,
                    total_score=%s
                WHERE id=%s
            """, (
                edu,
                q1_1, q1_2, q1_3, q1_4, q1_5,
                q2_1, q2_2, q2_3, q2_4, q2_5,
                q3,
                q4_1, q4_2,
                q5, q6, q7, q8,
                q9, q10, q11,
                mmse_total,
                row["id"],
            ))
        else:
            # INSERT
            cur.execute("""
                INSERT INTO assessment_mmse
                (patient_id, edu,
                 q1_1, q1_2, q1_3, q1_4, q1_5,
                 q2_1, q2_2, q2_3, q2_4, q2_5,
                 q3,
                 q4_1, q4_2,
                 q5, q6, q7, q8,
                 q9, q10, q11,
                 total_score)
                VALUES
                (%s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s,
                 %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s,
                 %s)
            """, (
                patient_id, edu,
                q1_1, q1_2, q1_3, q1_4, q1_5,
                q2_1, q2_2, q2_3, q2_4, q2_5,
                q3,
                q4_1, q4_2,
                q5, q6, q7, q8,
                q9, q10, q11,
                mmse_total,
            ))

        conn.commit()
        cur.close()
        conn.close()

        # อัปเดต mmse รวมใน patient_history
        conn2 = get_db_connection()
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE patient_history SET mmse=%s WHERE id=%s",
            (mmse_total, patient_id)
        )
        conn2.commit()
        cur2.close()
        conn2.close()

        # ==== ดูว่า user กดปุ่มไหน (nav) ====
        nav = request.form.get("nav", "step3")

        if nav == "step1":
            # ย้อนกลับไปขั้นตอนที่ 1
            return redirect(url_for("assess_session", hn=hn, gcn=gcn))

        if nav == "step3":
            # ไป step3 โดยพก mmse / edu ไปด้วย
            return redirect(url_for("affect_step", hn=hn, gcn=gcn,
                                    mmse=mmse_total, edu=edu))

        if nav == "summary":
            # ข้ามไปหน้าสรุปเลย (ถ้าคุณมีปุ่มแบบนี้ในหน้า MMSE)
            return redirect(url_for("cga_summary",
                                    hn=hn, gcn=gcn,
                                    mmse=mmse_total, edu=edu))

        # default
        return redirect(url_for("affect_step", hn=hn, gcn=gcn,
                                mmse=mmse_total, edu=edu))

    # ========== GET: เปิดหน้า MMSE (ดึงค่าที่เคยกรอก) ==========
    mmse_row = None
    conn = get_db_connection()
    if conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM assessment_mmse WHERE patient_id = %s", (patient_id,))
        mmse_row = cur.fetchone()
        cur.close()
        conn.close()

    mmse_current = mmse_row["total_score"] if mmse_row and mmse_row.get("total_score") is not None else 0
    edu_current  = mmse_row["edu"] if mmse_row and mmse_row.get("edu") is not None else ""

    return render_template(
        "mmse.html",
        hn=hn,
        gcn=gcn,
        step=2,
        mmse_row=mmse_row,
        mmse_current=mmse_current,
        edu_current=edu_current,
    )




@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT COUNT(*) AS total FROM patient_history")
    total = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS today FROM patient_history WHERE DATE(date_assessed) = CURDATE()")
    today = cur.fetchone()["today"]

    cur.execute("SELECT COUNT(*) AS week FROM patient_history WHERE YEARWEEK(date_assessed, 1) = YEARWEEK(CURDATE(), 1)")
    week = cur.fetchone()["week"]

    cur.execute("SELECT COUNT(*) AS month FROM patient_history WHERE MONTH(date_assessed) = MONTH(CURDATE())")
    month = cur.fetchone()["month"]

    conn.close()

    # ✅ สร้าง object รวมข้อมูล KPI
    kpis = {
        "total": total,
        "today": today,
        "week": week,
        "month": month
    }

    # ✅ เพิ่มตัวแปรอื่น ๆ สำหรับ chart
    bar_labels = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย."]
    bar_values = [12, 19, 3, 5, 2, 3]
    risk = {"สูง": 2, "ปานกลาง": 5, "ต่ำ": 10}

        # ====== เพิ่ม label วันที่/สัปดาห์/เดือน (แสดงบนการ์ด) ======
    today_date = date.today()
    week_start, week_end = get_week_range(today_date)

    today_label = format_th_date(today_date)
    week_label  = f"{format_th_date(week_start)} – {format_th_date(week_end)}"
    month_label = format_th_month(today_date)


    return render_template(
        "dashboard.html",
        kpis=kpis,  # ✅ ส่ง object kpis
        bar_labels=bar_labels,
        bar_values=bar_values,
        risk=risk,
        today_label=today_label,
        week_label=week_label,
        month_label=month_label,
    )

def parse_date_ymd(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except:
        return None


@app.route("/reports/summary", methods=["GET"], endpoint="report_summary")
def report_summary():
    # --- รับ period ---
    period = (request.args.get("period") or "month").strip()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    today = date.today()

    # --- คำนวณช่วงวันที่ ---
    if period == "today":
        start_date = today
        end_date = today
        period_label = format_th_date(today)

    elif period == "week":
        start_date, end_date = get_week_range(today)
        period_label = f"{format_th_date(start_date)} – {format_th_date(end_date)}"

    elif period == "custom" and start and end:
        # start/end เป็น YYYY-MM-DD
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except:
            start_date = today.replace(day=1)
            end_date = today
            period = "month"
        period_label = f"{format_th_date(start_date)} – {format_th_date(end_date)}"

    else:
        # month (default)
        start_date = today.replace(day=1)
        end_date = today
        period = "month"
        period_label = format_th_month(today)

    # ทำให้ end เป็น inclusive ใน SQL: ใช้ < end_next_day
    end_next = end_date + timedelta(days=1)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # --- KPI ---
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN mmse IS NOT NULL AND mmse < 24 THEN 1 ELSE 0 END) AS risk_mmse,
            SUM(CASE WHEN tgds IS NOT NULL AND tgds >= 6 THEN 1 ELSE 0 END) AS risk_tgds,
            SUM(CASE WHEN sra  IS NOT NULL AND sra  > 0 THEN 1 ELSE 0 END) AS risk_sra,
            SUM(CASE WHEN
                (mmse IS NOT NULL AND mmse < 24) OR
                (tgds IS NOT NULL AND tgds >= 6) OR
                (sra  IS NOT NULL AND sra  > 0)
            THEN 1 ELSE 0 END) AS at_risk
        FROM patient_history
        WHERE date_assessed >= %s AND date_assessed < %s
    """, (start_date, end_next))
    kpi = cur.fetchone() or {}

    total = int(kpi.get("total") or 0)
    at_risk = int(kpi.get("at_risk") or 0)
    donut = {
        "at_risk": at_risk,
        "normalish": max(total - at_risk, 0)
    }

    # --- Trend ต่อวัน ---
    cur.execute("""
        SELECT DATE(date_assessed) AS d, COUNT(*) AS c
        FROM patient_history
        WHERE date_assessed >= %s AND date_assessed < %s
        GROUP BY DATE(date_assessed)
        ORDER BY d ASC
    """, (start_date, end_next))
    rows = cur.fetchall() or []

    trend_labels = []
    trend_values = []
    for r in rows:
        d = r["d"]
        trend_labels.append(format_th_date(d))
        trend_values.append(int(r["c"] or 0))

    # --- Urgent: เรียง SRA สูงสุด ---
    cur.execute("""
        SELECT hn, gcn, name, surname, age, mmse, tgds, sra, date_assessed
        FROM patient_history
        WHERE date_assessed >= %s AND date_assessed < %s
          AND sra IS NOT NULL AND sra > 0
        ORDER BY sra DESC, date_assessed DESC
        LIMIT 10
    """, (start_date, end_next))
    urgent = cur.fetchall() or []

    # แปลงวันที่ urgent ให้เป็นไทย (สวย)
    for u in urgent:
        dt = u.get("date_assessed")
        if isinstance(dt, datetime):
            u["date_assessed"] = format_th_date(dt.date())
        elif isinstance(dt, date):
            u["date_assessed"] = format_th_date(dt)

    cur.close()
    conn.close()

    return render_template(
        "report_summary.html",
        period=period,
        period_label=period_label,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        kpi=kpi,
        donut=donut,
        trend_labels=trend_labels,
        trend_values=trend_values,
        urgent=urgent,
    )


@app.get("/assess/<hn>/<gcn>/report/full", endpoint="report_full")
def report_full(hn, gcn):
    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("cga_summary", hn=hn, gcn=gcn))

    cur = conn.cursor(dictionary=True)

    # 1) patient_history ล่าสุด
    cur.execute("""
        SELECT *
        FROM patient_history
        WHERE hn=%s AND gcn=%s
        ORDER BY id DESC
        LIMIT 1
    """, (hn, gcn))
    patient = cur.fetchone()

    if not patient:
        cur.close(); conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("patient_list"))

    patient_id = patient["id"]

    # 2) ดึงคำตอบแบบละเอียดจากตารางประเมิน (ของเดิมคุณ)
    cur.execute("SELECT * FROM assessment_mmse WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (patient_id,))
    mmse_row = cur.fetchone()

    cur.execute("SELECT * FROM assessment_tgds WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (patient_id,))
    tgds_row = cur.fetchone()

    cur.execute("SELECT * FROM assessment_sra WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (patient_id,))
    sra_row = cur.fetchone()

    cur.close(); conn.close()

    # 3) วันที่ประเมิน (พ.ศ.)
    assessed_dt = patient.get("date_assessed")
    if isinstance(assessed_dt, datetime):
        assessed_d = assessed_dt.date()
    elif isinstance(assessed_dt, date):
        assessed_d = assessed_dt
    else:
        assessed_d = date.today()
    assessed_th = format_th_date(assessed_d)

    # 4) คะแนนรวม (ใช้ค่าที่คุณเก็บไว้ใน patient_history ก่อน)
    mmse_total = int(patient.get("mmse") or 0)
    tgds_total = int(patient.get("tgds") or 0)
    sra_total  = int(patient.get("sra")  or 0)

    # 5) แปลผลแบบใช้งานจริง
    edu = str(patient.get("edu") or "")  # ถ้าคุณมี field edu; ถ้าไม่มีค่อยปรับ
    # ถ้าไม่มี edu ให้ใช้วิธีง่าย: มองว่า >ประถม (cutoff 22)
    def mmse_interp(score: int, edu_code: str):
        # ปรับ mapping edu ของคุณได้ทีหลัง
        # 0/1 = ไม่รู้หนังสือ, 2 = ประถม, else = >ประถม
        if edu_code in ("0", "1"):
            cutoff = 14
            edu_txt = "ไม่ได้เรียน/อ่านเขียนไม่ได้"
        elif edu_code in ("2",):
            cutoff = 17
            edu_txt = "ประถมศึกษา"
        else:
            cutoff = 22
            edu_txt = "สูงกว่าประถม"
        return (edu_txt, "สงสัยบกพร่อง" if score <= cutoff else "ปกติ", cutoff)

    edu_txt, mmse_flag, mmse_cutoff = mmse_interp(mmse_total, edu)

    if tgds_total <= 5:
        tgds_flag = "ไม่พบภาวะซึมเศร้า"
    elif tgds_total <= 10:
        tgds_flag = "สงสัยภาวะซึมเศร้า"
    else:
        tgds_flag = "มีภาวะซึมเศร้า"

    if sra_total == 0:
        sra_flag = "ไม่พบความเสี่ยง"
    elif sra_total <= 8:
        sra_flag = "เสี่ยงเล็กน้อย"
    elif sra_total <= 16:
        sra_flag = "เสี่ยงปานกลาง"
    else:
        sra_flag = "เสี่ยงรุนแรง"

    # 6) ข้อเสนอแนะสั้น ๆ (เอาไปใช้จริง)
    recs = []
    if sra_total >= 9:
        recs.append("ประเมินความปลอดภัย/เฝ้าระวังใกล้ชิด และพิจารณาส่งต่อจิตเวชเร่งด่วน")
    elif sra_total >= 1:
        recs.append("ให้คำแนะนำ/นัดติดตามความเสี่ยงฆ่าตัวตาย")

    if tgds_total >= 6:
        recs.append("คัดกรองซ้ำ/ประเมินต่อเพิ่มเติม และพิจารณาปรึกษาสหวิชาชีพหรือจิตเวช")

    if mmse_total <= mmse_cutoff:
        recs.append("พิจารณาประเมินต่อด้านความจำ/การทำกิจวัตร และติดตาม/ส่งต่อแพทย์")

    return render_template(
        "report_full.html",
        patient=patient,
        hn=hn, gcn=gcn,
        assessed_th=assessed_th,
        mmse_total=mmse_total, tgds_total=tgds_total, sra_total=sra_total,
        edu_txt=edu_txt, mmse_cutoff=mmse_cutoff,
        mmse_flag=mmse_flag, tgds_flag=tgds_flag, sra_flag=sra_flag,
        mmse_row=mmse_row, tgds_row=tgds_row, sra_row=sra_row,
        recs=recs
    )


@app.route("/assess/<hn>/<gcn>/summary", methods=["GET", "POST"], endpoint="cga_summary")
def cga_summary(hn, gcn):

    mmse = int(request.args.get("mmse", 0))
    tgds = int(request.args.get("tgds", 0))
    sra = int(request.args.get("sra", 0))
    edu = request.args.get("edu", "")

    # --- ดึงชื่อผู้ป่วยจาก patient_history ล่าสุด ---
    conn = get_db_connection()
    patient = None
    patient_history_id = None  # (ตัวแปรใหม่สำหรับเก็บ Key)
    
    if conn:
        cur = conn.cursor(dictionary=True)
        
        # (เรา "SELECT" เอา id (Key) และ hn, gcn ออกมาด้วย)
        cur.execute(
            "SELECT id, name, age, hn, gcn FROM patient_history WHERE hn = %s AND gcn = %s ORDER BY id DESC LIMIT 1",
            (hn, gcn)
        )
        patient = cur.fetchone()
        
        if patient:
            patient_history_id = patient["id"] # (เก็บ Key ไว้)
            
        cur.close()
        conn.close()

    # ตีความผลการประเมิน
    mmse_flag = "มีภาวะสมองเสื่อม" if mmse < 24 else "ปกติ"
    tgds_flag = "ไม่มีภาวะซึมเศ้า" if tgds < 6 else "สงสัยซึมเศร้า"
    sra_flag = "ไม่พบความเสี่ยง" if sra == 0 else "ต้องส่งต่อด่วน!"

    today_th = format_th_date(date.today())

 # ดึง notes ย้อนหลัง
    conn = get_db_connection()
    notes = []
    if conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT note, created_at FROM assessment_notes WHERE hn = %s AND gcn = %s ORDER BY created_at DESC",
            (hn, gcn)
        )
        notes = cur.fetchall()
        cur.close()
        conn.close()

    # "อัปเดต" ข้อมูลคะแนน (โดยใช้ Key)
    conn = get_db_connection()
    
    if conn and patient_history_id: 
        cur = conn.cursor()
        
        sql = """
            UPDATE patient_history 
            SET mmse = %s, tgds = %s, sra = %s
            WHERE id = %s 
        """
        
        data = (mmse, tgds, sra, patient_history_id) 
        
        cur.execute(sql, data)
        conn.commit()
        cur.close()
        conn.close()

        assessed_dt = patient.get("date_assessed") if patient else None
        if isinstance(assessed_dt, datetime):
            assessed_d = assessed_dt.date()
        elif isinstance(assessed_dt, date):
            assessed_d = assessed_dt
        else:
            assessed_d = date.today()

        today_th = format_th_date(assessed_d)


        # --- เริ่มโค้ดแปลผลคะแนน ---

    # 1. แปลผล MMSE (สมรรถภาพสมอง)
    # (เกณฑ์นี้จะแม่นยำขึ้นถ้าเราใช้ค่า 'edu' มาคำนวณ แต่ตอนนี้จะใช้เกณฑ์มาตรฐานก่อน)
    mmse_interp = ""
    if mmse <= 21:
        mmse_interp = "มีภาวะสมองเสื่อม"
    elif mmse <= 26:
        mmse_interp = "มีภาวะสมองเสื่อมเล็กน้อย"
    else:
        mmse_interp = "ปกติ"

    # 2. แปลผล TGDS-15 (ภาวะซึมเศร้า)
    tgds_interp = ""
    if tgds >= 6:
        tgds_interp = "มีภาวะซึมเศร้า"
    elif tgds >= 4: # (คือ 4-5 คะแนน)
        tgds_interp = "เสี่ยงภาวะซึมเศร้า"
    else: # (คือ 0-3 คะแนน)
        tgds_interp = "ไม่พบภาวะซึมเศร้า"

    # 3. แปลผล 8Q (ความเสี่ยงฆ่าตัวตาย)
    sra_interp = ""
    if sra >= 17:
        sra_interp = "มีความเสี่ยงฆ่าตัวตายรุนแรง"
    elif sra >= 9:
        sra_interp = "มีความเสี่ยงฆ่าตัวตายปานกลาง"
    elif sra > 0: # (คือ 1-8 คะแนน)
        sra_interp = "มีความเสี่ยงฆ่าตัวตายเล็กน้อย"
    else: # (คือ 0 คะแนน)
        sra_interp = "ไม่พบความเสี่ยง"

    # ⭐️⭐️⭐️ (นี่คือ "return" ที่ย่อหน้าถูกต้องแล้ว) ⭐️⭐️⭐️
    # มันอยู่ "ข้างใน" def cga_summary
    return render_template(
        "summary.html",
        patient=patient,
        hn=hn, gcn=gcn, date=today_th,
        mmse=mmse, mmse_flag=mmse_interp, edu=edu,  # <-- แก้ mmse_flag
        tgds=tgds, tgds_flag=tgds_interp,        # <-- แก้ tgds_flag
        sra=sra, sra_flag=sra_interp,
        notes=notes,
        step=4,
    )

@app.route("/assess/<hn>/<gcn>/summary/notes", methods=["POST"])
def add_summary_note(hn, gcn):
    note = request.form.get("note", "").strip()
    if note:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO assessment_notes (hn, gcn, note) VALUES (%s, %s, %s)",
            (hn, gcn, note)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("บันทึกคำแนะนำเพิ่มเติมแล้ว", "success")

    return redirect(url_for("cga_summary", hn=hn, gcn=gcn))

@app.route("/assess/<hn>/<gcn>/ai_analysis", methods=["GET"])
def ai_analysis(hn, gcn):
    # 1) ดึง feature จาก patient_history ล่าสุด
    data = get_ai_features_from_db(hn, gcn)
    if not data:
        flash("ยังไม่มีข้อมูลประเมินสำหรับ HN/GCN นี้", "error")
        return redirect(url_for("assess_session", hn=hn, gcn=gcn))

    # 2) เรียก AI model
    ai_raw = predict_all(
        age        = data["age"],
        mmse_score = data["mmse_score"],
        tgds_score = data["tgds_score"],
        q8_score   = data["q8_score"],
        hl_score   = data["hl_score"],
        hr_score   = data["hr_score"],
        vr_score   = data["vr_score"],
        vl_score   = data["vl_score"],
    )

    # 3) แปล label เป็นข้อความไทย
    def txt(label, pos, neg):
        return pos if label == 1 else neg

    cognitive_text  = txt(ai_raw["cognitive"]["label"],
                          "สงสัยบกพร่องด้านรู้คิด",
                          "ไม่สงสัยบกพร่องด้านรู้คิด")
    depression_text = txt(ai_raw["depression"]["label"],
                          "มีภาวะซึมเศร้า",
                          "ไม่พบภาวะซึมเศร้า")
    suicide_text    = txt(ai_raw["suicide"]["label"],
                          "มีความเสี่ยงฆ่าตัวตาย",
                          "ไม่พบความเสี่ยงฆ่าตัวตาย")

    # 4) สร้างสรุปส่งไป template (ให้รูปแบบใกล้ของเดิม)
    ai_summary = {
        "cognitive":     cognitive_text,
        "depression":    depression_text,
        "suicide_risk":  suicide_text,
        "recommendations": [
            "พิจารณาเฝ้าระวังอาการซึมเศร้า" if ai_raw["depression"]["label"] == 1 else "ติดตามอาการตามปกติ",
            "พิจารณาส่งต่อด้านจิตเวช" if ai_raw["suicide"]["label"] == 1 else "ยังไม่พบสัญญาณเสี่ยงชัดเจน"
        ]
    }

    # 5) คำนวณวันที่ไทย (เหมือนเดิม)
    now = datetime.now()
    thai_months = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    thaidate_str = f"{now.day} {thai_months[now.month - 1]} {now.year + 543}"

    patient_data = {
        "name": data["name"],
        "hn": hn,
        "gcn": gcn,
    }

    # 6) ส่งค่าไปหน้า ai_analysis.html
    return render_template(
        "ai_analysis.html",
        patient=patient_data,
        ai_summary=ai_summary,
        thaidate=thaidate_str,
        ai_raw=ai_raw,     # เผื่ออยากโชว์เปอร์เซ็นต์ในหน้า HTML ทีหลัง
    )


@app.route("/ai-chat", methods=["POST"])
def ai_chat():
    data = request.get_json() or {}
    user_msg = (data.get("message") or "").strip()
    context = data.get("context") or {}

    hn = (context.get("hn") or "").strip() or None
    gcn = (context.get("gcn") or "").strip() or None
    patient_name = (context.get("name") or "").strip() or None
    page = (context.get("page") or "").strip() or None

    if not user_msg:
        return jsonify({"reply": "ลองพิมพ์คำถามหรือสิ่งที่อยากปรึกษาก่อนนะคะ 😊"})

    # 🧠 ตรงนี้ตอนนี้ยังเป็น “AI จำลอง”
    # ทีหลังคุณสามารถเปลี่ยนให้เรียก OpenAI / โมเดลจริงได้เลย
    base_reply = []

    if patient_name:
        base_reply.append(f"ตอนนี้คุณกำลังถามเกี่ยวกับผู้ป่วย: {patient_name}")
        if hn or gcn:
            base_reply.append(f"(HN: {hn or '-'}, GCN: {gcn or '-'})")

    if page:
        base_reply.append(f"หน้าปัจจุบัน: {page}")

    base_reply.append("")
    base_reply.append("ตอนนี้ระบบยังไม่ได้เชื่อมต่อโมเดล AI จริง จึงตอบในรูปแบบคำแนะนำทั่วไปนะคะ 🙏")
    base_reply.append(f"คำถามของคุณคือ:\n“{user_msg}”")
    base_reply.append("")
    base_reply.append("ข้อเสนอแนะเบื้องต้น:\n- ตรวจสอบคะแนนประเมินล่าสุด (MMSE / TGDS / 8Q)\n- พิจารณาปัจจัยร่วม เช่น อายุ โรคประจำตัว\n- หากพบความเสี่ยงสูง ควรปรึกษาแพทย์หรือทีมสหวิชาชีพทันที")

    reply_text = "\n".join(base_reply)

    # 💾 บันทึกลงฐานข้อมูล
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ai_chat_logs (hn, gcn, patient_name, page, user_message, ai_reply)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (hn, gcn, patient_name, page, user_msg, reply_text))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print("⚠️ Error saving ai_chat_logs:", e)

    return jsonify({"reply": reply_text})


@app.route("/affect-step/<hn>/<gcn>", methods=["GET", "POST"], strict_slashes=False)
def affect_step(hn, gcn):
    patient_id = get_patient_id_by_hn_gcn(hn, gcn)
    if not patient_id:
        flash("ยังไม่มีข้อมูลขั้นตอนที่ 1 สำหรับ HN/GCN นี้", "error")
        return redirect(url_for("assess_session", hn=hn, gcn=gcn))

    if request.method == "POST":
        # ---------- อ่านค่าจากฟอร์ม ----------
        try:
            mmse = int(request.form.get("mmse", 0) or 0)
        except ValueError:
            mmse = 0
        edu = request.form.get("edu") or ""

        # ---------- TGDS-15 ----------
        no_points  = [1, 5, 7, 11, 13]
        yes_points = [2, 3, 4, 6, 8, 9, 10, 12, 14, 15]

        tgds_score  = 0
        tgds_values = {}

        for i in range(1, 16):
            ans = request.form.get(f"tgds_{i}")  # "yes"/"no"/None
            tgds_values[i] = ans
            if i in yes_points and ans == "yes":
                tgds_score += 1
            if i in no_points and ans == "no":
                tgds_score += 1

        # 👇 ใหม่: แปลง yes/no → 1/0 สำหรับเก็บลง DB
        tgds_values_db = {}
        for i in range(1, 16):
            ans = tgds_values[i]
            if ans == "yes":
                tgds_values_db[i] = 1
            elif ans == "no":
                tgds_values_db[i] = 0
            else:
                tgds_values_db[i] = None

        # ---------- 8Q / SRA ----------
        sra_score  = 0
        sra_values = {}

        for i in range(1, 9):
            ans = request.form.get(f"sra_{i}")   # "0"/"1"/None
            if ans is not None:
                val = int(ans)
            else:
                val = None
            sra_values[i] = val
            if val == 1:
                sra_score += 1

        # ---------- บันทึกลง assessment_tgds / assessment_sra ----------
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # ===== TGDS =====
        cur.execute("SELECT id FROM assessment_tgds WHERE patient_id = %s", (patient_id,))
        row_t = cur.fetchone()

        if row_t:
            cur.execute(
                """
                UPDATE assessment_tgds
                SET q1=%s, q2=%s, q3=%s, q4=%s, q5=%s,
                    q6=%s, q7=%s, q8=%s, q9=%s, q10=%s,
                    q11=%s, q12=%s, q13=%s, q14=%s, q15=%s,
                    total_score=%s,
                    updated_at = NOW()
                WHERE id=%s
                """,
                (
                    tgds_values_db[1], tgds_values_db[2], tgds_values_db[3], tgds_values_db[4], tgds_values_db[5],
                    tgds_values_db[6], tgds_values_db[7], tgds_values_db[8], tgds_values_db[9], tgds_values_db[10],
                    tgds_values_db[11], tgds_values_db[12], tgds_values_db[13], tgds_values_db[14], tgds_values_db[15],
                    tgds_score,
                    row_t["id"],
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO assessment_tgds (
                    patient_id,
                    q1, q2, q3, q4, q5,
                    q6, q7, q8, q9, q10,
                    q11, q12, q13, q14, q15,
                    total_score, updated_at
                ) VALUES (
                    %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, NOW()
                )
                """,
                (
                    patient_id,
                    tgds_values_db[1], tgds_values_db[2], tgds_values_db[3], tgds_values_db[4], tgds_values_db[5],
                    tgds_values_db[6], tgds_values_db[7], tgds_values_db[8], tgds_values_db[9], tgds_values_db[10],
                    tgds_values_db[11], tgds_values_db[12], tgds_values_db[13], tgds_values_db[14], tgds_values_db[15],
                    tgds_score,
                ),
            )

        # ===== SRA =====
        cur.execute("SELECT id FROM assessment_sra WHERE patient_id = %s", (patient_id,))
        row_s = cur.fetchone()

        if row_s:
            cur.execute(
                """
                UPDATE assessment_sra
                SET q1=%s, q2=%s, q3=%s, q4=%s,
                    q5=%s, q6=%s, q7=%s, q8=%s,
                    total_score=%s,
                    updated_at = NOW()
                WHERE id=%s
                """,
                (
                    sra_values[1], sra_values[2], sra_values[3], sra_values[4],
                    sra_values[5], sra_values[6], sra_values[7], sra_values[8],
                    sra_score,
                    row_s["id"],
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO assessment_sra (
                    patient_id,
                    q1, q2, q3, q4, q5, q6, q7, q8,
                    total_score, updated_at
                ) VALUES (
                    %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, NOW()
                )
                """,
                (
                    patient_id,
                    sra_values[1], sra_values[2], sra_values[3], sra_values[4],
                    sra_values[5], sra_values[6], sra_values[7], sra_values[8],
                    sra_score,
                ),
            )

        conn.commit()
        cur.close()
        conn.close()

        # log + update summary
        save_log(session.get("user"), "บันทึก TGDS/SRA", hn, gcn,
                 detail=f"TGDS={tgds_score}, SRA={sra_score}")

        conn2 = get_db_connection()
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE patient_history SET tgds=%s, sra=%s WHERE id=%s",
            (tgds_score, sra_score, patient_id),
        )
        conn2.commit()
        cur2.close()
        conn2.close()

        # ---------- ตัดสินใจไปหน้าไหนต่อ ----------
        nav = request.form.get("nav", "summary")

        if nav == "step1":
            return redirect(url_for("assess_session", hn=hn, gcn=gcn))

        if nav == "step2":
            return redirect(url_for("mmse_next", hn=hn, gcn=gcn, mmse=mmse, edu=edu))

        return redirect(
            url_for("cga_summary",
                    hn=hn, gcn=gcn,
                    mmse=mmse, tgds=tgds_score,
                    sra=sra_score, edu=edu)
        )

    # ---------- GET: โหลดค่าที่เคยกรอก ----------
    mmse = request.args.get("mmse", 0)
    edu = request.args.get("edu", "")

    tgds_row = None
    sra_row = None

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM assessment_tgds WHERE patient_id = %s", (patient_id,))
    tgds_row = cur.fetchone()
    cur.execute("SELECT * FROM assessment_sra WHERE patient_id = %s", (patient_id,))
    sra_row = cur.fetchone()
    cur.close()
    conn.close()

    return render_template(
        "affect.html",
        hn=hn,
        gcn=gcn,
        step=3,
        mmse_current=mmse,
        edu_current=edu,
        tgds_row=tgds_row,
        sra_row=sra_row,
    )


   
   # ------------------- จัดการข้อมูลผู้ป่วย -------------------
@app.route("/patients")
def patient_list():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # --- รองรับทั้งแบบ search ช่องเดียว (เผื่อยังมีใช้อยู่) ---
    search = (request.args.get("search") or "").strip()

    # --- แบบใหม่: แยกตาม attribute ---
    name = (request.args.get("name") or "").strip()
    hn = (request.args.get("hn") or "").strip()
    gcn = (request.args.get("gcn") or "").strip()
    disease = (request.args.get("disease") or "").strip()
    risk = (request.args.get("risk") or "").strip()

    where = []
    params = []

    # ถ้าคุณยังอยากให้ "search" ช่องเดียวทำงานด้วย
    if search:
        like = f"%{search}%"
        where.append("""
            (
              name LIKE %s OR
              hn LIKE %s OR
              gcn LIKE %s OR
              CAST(age AS CHAR) LIKE %s OR
              disease LIKE %s OR
              risk_level LIKE %s
            )
        """)
        params.extend([like, like, like, like, like, like])

    # ช่องแยก (AND กัน)
    if name:
        where.append("name LIKE %s")
        params.append(f"%{name}%")

    if hn:
        where.append("hn LIKE %s")
        params.append(f"%{hn}%")

    if gcn:
        where.append("gcn LIKE %s")
        params.append(f"%{gcn}%")

    if disease:
        where.append("disease LIKE %s")
        params.append(f"%{disease}%")

    if risk:
        # ✅ สำคัญ: ถ้าหน้า select ส่งเป็น ไทย (ต่ำ/ปานกลาง/สูง) ก็เทียบตรงๆ ได้เลย
        where.append("risk_level = %s")
        params.append(risk)

        # ถ้าหน้า select ยังส่ง low/mid/high ให้ใช้ mapping แทน:
        # mapping = {"low": "ต่ำ", "mid": "ปานกลาง", "high": "สูง"}
        # where.append("risk_level = %s")
        # params.append(mapping.get(risk, risk))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT *
        FROM patient_history
        {where_sql}
        ORDER BY id DESC
    """

    cur.execute(sql, params)
    patients = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("patients.html", patients=patients)



@app.route("/patients/add", methods=["GET", "POST"])
def add_patient():
    if request.method == "POST":
        name = request.form["name"]
        hn = request.form["hn"]
        gcn = request.form["gcn"]
        age = request.form["age"]
        gender = request.form["gender"]
        disease = request.form["disease"]
        risk_level = request.form["risk_level"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO patient_history (name, hn, gcn, age, gender, disease, risk_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (name, hn, gcn, age, gender, disease, risk_level)
        )
        conn.commit()
        conn.close()
        flash("เพิ่มข้อมูลผู้ป่วยเรียบร้อยแล้ว", "success")
        return redirect(url_for("patient_list"))
    return render_template("patient_form.html", mode="add")


@app.route("/patients/edit/<int:id>", methods=["GET", "POST"])
def edit_patient(id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # ดึงข้อมูลคนไข้มาแสดงในฟอร์ม
    cur.execute("SELECT * FROM patient_history WHERE id=%s", (id,))
    patient = cur.fetchone()

    if not patient:
        cur.close()
        conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("patient_list"))

    def to_int_or_none(v):
        v = (v or "").strip()
        if v == "" or v.lower() == "none":
            return None
        try:
            return int(v)
        except ValueError:
            return None

    if request.method == "POST":
        # ===== รับค่าจากฟอร์ม (แก้เฉพาะข้อมูลผู้ป่วย) =====
        name = (request.form.get("name") or "").strip()
        hn = (request.form.get("hn") or "").strip()
        gcn = (request.form.get("gcn") or "").strip()
        gender = (request.form.get("gender") or "").strip()
        disease = (request.form.get("disease") or "").strip()
        risk_level = (request.form.get("risk_level") or "").strip()
        age = to_int_or_none(request.form.get("age"))

        # ✅ ไม่รับ mmse/tgds/sra จากหน้านี้แล้ว
        cur.execute("""
            UPDATE patient_history
            SET name=%s, hn=%s, gcn=%s, age=%s, gender=%s, disease=%s,
                risk_level=%s
            WHERE id=%s
        """, (name, hn, gcn, age, gender, disease, risk_level, id))

        conn.commit()
        cur.close()
        conn.close()
        flash("แก้ไขข้อมูลสำเร็จ", "success")
        return redirect_back()


        # ===== GET =====
    # ดึงคำตอบการประเมินล่าสุดของคนนี้ (จากตาราง assessment_...)
    cur.execute("SELECT * FROM assessment_mmse WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (id,))
    mmse_detail = cur.fetchone()

    cur.execute("SELECT * FROM assessment_tgds WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (id,))
    tgds_detail = cur.fetchone()

    cur.execute("SELECT * FROM assessment_sra WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (id,))
    sra_detail = cur.fetchone()

    # แปลงเป็น list ที่อ่านออก (มี label)
    mmse_items = map_answers(mmse_detail, MMSE_QUESTIONS)
    tgds_items = map_answers(tgds_detail, TGDS_QUESTIONS)
    sra_items  = map_answers(sra_detail,  SRA_QUESTIONS)

    cur.close()
    conn.close()

    return render_template(
        "patient_form.html",
        patient=patient,
        mode="edit",
        mmse_detail=mmse_detail,
        tgds_detail=tgds_detail,
        sra_detail=sra_detail,
        mmse_items=mmse_items,
        tgds_items=tgds_items,
        sra_items=sra_items,
    )





@app.route("/patients/delete/<int:id>", methods=["POST"])
def delete_patient(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM patient_history WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("ลบข้อมูลเรียบร้อยแล้ว", "success")
    return redirect(url_for("patient_list"))

@app.route("/patients/<int:id>/history")
def patient_history(id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1) ดึงผู้ป่วย (session ที่กดเข้ามา)
    cur.execute("SELECT * FROM patient_history WHERE id=%s", (id,))
    patient = cur.fetchone()
    if not patient:
        cur.close()
        conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("patient_list"))

    hn = patient.get("hn")
    gcn = patient.get("gcn")

    # 2) ดึงทุก session ของ HN/GCN นี้
    assessments = []
    if hn and gcn:
        cur.execute("""
            SELECT id, date_assessed
            FROM patient_history
            WHERE hn=%s AND gcn=%s
            ORDER BY date_assessed DESC, id DESC
        """, (hn, gcn))
        assessments = cur.fetchall()

    # กันหน้าโล่ง
    if not assessments:
        assessments = [{
            "id": patient["id"],
            "date_assessed": patient.get("date_assessed"),
        }]

    # =========================
    # helpers (ต้องอยู่ก่อน for-loop)
    # =========================
    ALLOWED_TABLES = {"assessment_mmse", "assessment_tgds", "assessment_sra"}

    def latest_row(table: str, pid: int):
        if table not in ALLOWED_TABLES:
            return None
        cur.execute(
            f"SELECT * FROM {table} WHERE patient_id=%s ORDER BY id DESC LIMIT 1",
            (pid,)
        )
        return cur.fetchone()

    def total_from_latest_row(table: str, pid: int) -> int:
        row = latest_row(table, pid)
        if not row:
            return 0

        total = 0
        for k, v in row.items():
            if k in ("id", "patient_id", "edu", "created_at", "updated_at"):
                continue
            if isinstance(v, (int, float)):
                total += int(v)
        return total

    # =========================
    # 3) เติมคะแนน + รายละเอียด
    # =========================
    for a in assessments:
        pid = a["id"]

        # รายละเอียด (ไว้กดดู)
        a["mmse_detail"] = latest_row("assessment_mmse", pid)
        a["tgds_detail"] = latest_row("assessment_tgds", pid)
        a["sra_detail"]  = latest_row("assessment_sra", pid)

        # คะแนนรวม
        a["mmse"] = total_from_latest_row("assessment_mmse", pid)
        a["tgds"] = total_from_latest_row("assessment_tgds", pid)
        a["sra"]  = total_from_latest_row("assessment_sra", pid)

    # 4) Notes
    cur.execute("""
        SELECT note, created_at
        FROM assessment_notes
        WHERE hn=%s AND gcn=%s
        ORDER BY created_at DESC
    """, (hn, gcn))
    notes = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "patient_history.html",
        patient=patient,
        assessments=assessments,
        notes=notes
    )

@app.route("/patients/<int:id>/trend", endpoint="patient_trend")
def patient_trend(id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1) ดึงผู้ป่วยหลัก
    cur.execute("SELECT * FROM patient_history WHERE id=%s", (id,))
    patient = cur.fetchone()
    if not patient:
        cur.close()
        conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("patient_list"))

    hn = patient.get("hn")
    gcn = patient.get("gcn")

    # 2) ดึงทุก session ของคนนี้ (ตาม HN/GCN)
    sessions = []
    if hn and gcn:
        cur.execute("""
            SELECT id, date_assessed
            FROM patient_history
            WHERE hn=%s AND gcn=%s
            ORDER BY date_assessed ASC, id ASC
        """, (hn, gcn))
        sessions = cur.fetchall()

    if not sessions:
        sessions = [{"id": patient["id"], "date_assessed": patient.get("date_assessed")}]

    ALLOWED_TABLES = {"assessment_mmse", "assessment_tgds", "assessment_sra"}

    def latest_row(table: str, pid: int):
        if table not in ALLOWED_TABLES:
            return None
        cur.execute(f"SELECT * FROM {table} WHERE patient_id=%s ORDER BY id DESC LIMIT 1", (pid,))
        return cur.fetchone()

    def total_from_latest_row(table: str, pid: int) -> int:
        row = latest_row(table, pid)
        if not row:
            return 0
        total = 0
        for k, v in row.items():
            if k in ("id", "patient_id", "edu", "created_at", "updated_at"):
                continue
            if isinstance(v, (int, float)):
                total += int(v)
        return total

    # 3) สร้าง series คะแนนตามเวลา
    points = []
    for s in sessions:
        pid = s["id"]
        points.append({
            "id": pid,
            "date_assessed": s.get("date_assessed"),
            "mmse": total_from_latest_row("assessment_mmse", pid),
            "tgds": total_from_latest_row("assessment_tgds", pid),
            "sra":  total_from_latest_row("assessment_sra", pid),
        })

    # 4) latest / previous / delta
    latest = points[-1] if points else {"mmse": 0, "tgds": 0, "sra": 0, "date_assessed": None}
    prev   = points[-2] if len(points) >= 2 else None

    def delta(curr: int, prevv: int | None):
        if prevv is None:
            return None
        return curr - prevv

    mmse_delta = delta(latest["mmse"], prev["mmse"] if prev else None)
    tgds_delta = delta(latest["tgds"], prev["tgds"] if prev else None)
    sra_delta  = delta(latest["sra"],  prev["sra"]  if prev else None)

    # 5) แปลผล (ปรับ threshold ได้)
    def mmse_level(score: int):
        # ตัวอย่าง threshold ทั่วไป (ปรับให้ตรงงานคุณได้)
        if score >= 24:
            return ("ปกติ", "green")
        elif score >= 18:
            return ("เฝ้าระวัง", "amber")
        else:
            return ("เสี่ยงสูง", "red")

    def tgds_level(score: int):
        # TGDS-15 บ่อย ๆ ใช้ >= 6 เป็นเสี่ยง
        if score <= 5:
            return ("ปกติ", "green")
        elif score <= 9:
            return ("เฝ้าระวัง", "amber")
        else:
            return ("เสี่ยงสูง", "red")

    def sra_level(score: int):
        # ตัวอย่าง (เพราะ SRA ของคุณเป็นผลรวมจากข้อ)
        if score == 0:
            return ("ต่ำ", "green")
        elif score <= 2:
            return ("ปานกลาง", "amber")
        else:
            return ("สูง", "red")

    mmse_label, mmse_color = mmse_level(latest["mmse"])
    tgds_label, tgds_color = tgds_level(latest["tgds"])
    sra_label,  sra_color  = sra_level(latest["sra"])

    summary = {
        "last_date": latest.get("date_assessed"),
        "mmse_last": latest["mmse"], "mmse_delta": mmse_delta, "mmse_label": mmse_label, "mmse_color": mmse_color,
        "tgds_last": latest["tgds"], "tgds_delta": tgds_delta, "tgds_label": tgds_label, "tgds_color": tgds_color,
        "sra_last":  latest["sra"],  "sra_delta":  sra_delta,  "sra_label":  sra_label,  "sra_color":  sra_color,
        "n_points": len(points)
    }

    cur.close()
    conn.close()

    return render_template(
        "patient_trend.html",
        patient=patient,
        summary=summary,
        points=points,   # ถ้าอนาคตจะทำกราฟ
    )

@app.get("/patients/<int:patient_id>/mmse/edit")
def mmse_edit(patient_id):
    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "error")
        return redirect(url_for("patient_list"))

    cur = conn.cursor(dictionary=True)

    # 1) เอา hn/gcn ของ record นี้
    cur.execute("SELECT hn, gcn FROM patient_history WHERE id=%s", (patient_id,))
    p = cur.fetchone()

    # 2) เช็ค session-based (ระบบใหม่)
    base = _get_latest_session(conn, patient_id, "MMSE")

    # ✅ ถ้าไม่มี session-based แต่มีข้อมูล MMSE ในตารางเดิม -> พาไปหน้าเดิมที่กรอก
    if not base and p and p.get("hn") and p.get("gcn"):
        cur.execute("SELECT id FROM assessment_mmse WHERE patient_id=%s LIMIT 1", (patient_id,))
        legacy = cur.fetchone()
        cur.close()
        conn.close()

        if legacy:
            flash("ระบบแก้ไขแบบใหม่ยังไม่มีข้อมูล → เปิดหน้า MMSE เดิมให้แก้ไขแทน", "info")
            return redirect(url_for("mmse_next", hn=p["hn"], gcn=p["gcn"]))

    # ถ้ามี session-based ก็ใช้หน้าแก้ไขแบบใหม่ตามเดิม
    answers = _get_answers(conn, base["id"]) if base else {}
    cur.close()
    conn.close()

    if not base:
        flash("ยังไม่มี MMSE ให้แก้ไข", "error")
        return redirect(url_for("patient_list"))

    return render_template("mmse_edit.html",
                           patient_id=patient_id,
                           base=base,
                           answers=answers)


@app.post("/patients/<int:patient_id>/mmse/edit")
def mmse_edit_save(patient_id):
    reason = (request.form.get("reason") or "").strip()
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        base = _get_latest_session(conn, patient_id, "MMSE")
        if not base:
            flash("ยังไม่มี MMSE ให้แก้ไข", "error")
            return redirect(url_for("mmse_edit", patient_id=patient_id))

        base_id = base["id"]
        user_id = session.get("user_id")

        # สร้าง session ใหม่
        cur.execute("""
            INSERT INTO assessment_sessions (patient_id, form_code, status, created_by_user_id, note)
            VALUES (%s,'MMSE','corrected',%s,%s)
        """, (patient_id, user_id, reason or None))
        new_id = cur.lastrowid

        # copy คำตอบเดิม
        cur.execute("""
            INSERT INTO assessment_answers (session_id, question_code, answer_value, answer_json)
            SELECT %s, question_code, answer_value, answer_json
            FROM assessment_answers
            WHERE session_id=%s
        """, (new_id, base_id))

        # upsert คำตอบใหม่
        for i in range(1, 31):
            key = f"Q{i}"
            val = request.form.get(key)
            if val is None:
                continue
            cur.execute("""
                INSERT INTO assessment_answers (session_id, question_code, answer_value)
                VALUES (%s,%s,%s)
                ON DUPLICATE KEY UPDATE answer_value=VALUES(answer_value)
            """, (new_id, key, val))

        # คำนวณคะแนน
        cur.execute("SELECT question_code, answer_value FROM assessment_answers WHERE session_id=%s", (new_id,))
        rows = cur.fetchall()
        ans = {r["question_code"]: (r["answer_value"] or "0") for r in rows}
        total = _compute_mmse(ans)

        cur.execute("INSERT INTO assessment_scores (session_id, total_score) VALUES (%s,%s)", (new_id, total))

        cur.execute("""
            INSERT INTO assessment_revisions (patient_id, form_code, base_session_id, new_session_id,
                                              corrected_by_user_id, reason)
            VALUES (%s,'MMSE',%s,%s,%s,%s)
        """, (patient_id, base_id, new_id, user_id, reason or None))

        conn.commit()
        flash("บันทึกการแก้ไข MMSE เรียบร้อย", "success")
        return redirect(url_for("mmse_edit", patient_id=patient_id))

    except Exception as e:
        conn.rollback()
        flash(f"บันทึกไม่สำเร็จ: {e}", "error")
        return redirect_back()

    finally:
        cur.close()
        conn.close()


@app.route("/assess/<hn>/<gcn>", methods=["GET", "POST"])
def assess_session(hn, gcn):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # ---- ดึงข้อมูลเดิมของ HN/GCN นี้ล่าสุด (ถ้ามี) ----
    cur.execute(
        """
        SELECT *
        FROM patient_history
        WHERE hn = %s AND gcn = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (hn, gcn),
    )
    patient = cur.fetchone()

    # ================== POST: กด submit ฟอร์ม ==================
    if request.method == "POST":
        # -------- 1) อ่านค่าจากฟอร์มทั้งหมด --------
        first_name = (request.form.get("name") or "").strip()
        surname    = (request.form.get("surname") or "").strip()
        age        = request.form.get("age") or None
        gender     = request.form.get("gender") or None      # ชาย / หญิง
        phone      = (request.form.get("phone") or "").strip() or None

        # ใหม่เพิ่ม
        address    = (request.form.get("address") or "").strip() or None
        marry      = request.form.get("marry") or None       # โสด / สมรส / ...
        num_people = request.form.get("num_people") or None  # จำนวนคนอยู่ด้วย
        live       = request.form.get("live") or None        # alone / family / caregiver

        smoke      = request.form.get("smoke") or None       # no/yes/quit
        alcohol    = request.form.get("alcohol") or None     # no/sometimes/daily
        height     = request.form.get("height") or None      # ส่วนสูง
        weight     = request.form.get("weight") or None      # น้ำหนัก
        waist      = request.form.get("waist") or None       # รอบเอว

        # วันเกิด (ฝั่ง hidden ที่เป็น ค.ศ.)
        birthdate  = request.form.get("birthdate") or None   # รูปแบบ YYYY-MM-DD

        # ถ้าไม่กรอกชื่อ ให้เก็บเป็น "ไม่ระบุชื่อ"
        if not first_name:
            first_name = "ไม่ระบุชื่อ"

                # ---- โรคประจำตัว ----
        selected_diseases = request.form.getlist("disease")  # list ของ checkbox ที่ติ๊ก
        disease_other = (request.form.get("disease_other") or "").strip()

        if disease_other:
            selected_diseases.append(f"อื่น ๆ: {disease_other}")

        disease = ",".join(selected_diseases) if selected_diseases else None


        # แปลงตัวเลขให้เป็น int/float ถ้าอยากให้ชัวร์ (ไม่บังคับ)
        # ถ้าคอลัมน์ใน DB เป็น INT/DECIMAL ทำแบบนี้จะปลอดภัยกว่า
        def to_int_or_none(v):
            try:
                return int(v) if v not in (None, "") else None
            except:
                return None

        height_cm = to_int_or_none(height)
        weight_kg = to_int_or_none(weight)
        waist_cm  = to_int_or_none(waist)
        num_ppl   = to_int_or_none(num_people)

        hearing_left    = request.form.get("hearing_left")
        hearing_right   = request.form.get("hearing_right")
        vision_snellen  = request.form.get("vision_snellen")


        # -------- 2) UPDATE / INSERT ลง patient_history --------
                # -------- 2) UPDATE / INSERT ลง patient_history -------
        if patient:
            # ---- มี record เดิม -> UPDATE ----
            cur.execute(
                """
                UPDATE patient_history
                SET name           = %s,
                    surname        = %s,
                    age            = %s,
                    gender         = %s,
                    phone          = %s,
                    disease        = %s,
                    address        = %s,
                    marry          = %s,
                    num_people     = %s,
                    live           = %s,
                    smoke          = %s,
                    alcohol        = %s,
                    height_cm      = %s,
                    weight_kg      = %s,
                    waist_cm       = %s,
                    birthdate      = %s,
                    hearing_left   = %s,
                    hearing_right  = %s,
                    vision_snellen = %s,
                    date_assessed  = NOW()
                WHERE id = %s
                """,
                (
                    first_name, surname, age, gender, phone, disease,
                    address, marry, num_ppl, live,
                    smoke, alcohol, height_cm, weight_kg, waist_cm,
                    birthdate,
                    hearing_left, hearing_right, vision_snellen,
                    patient["id"],
                ),
            )
        else:
            # ---- ยังไม่มี -> INSERT ใหม่ ----
            cur.execute(
                """
                INSERT INTO patient_history
                    (hn, gcn,
                     name, surname, age, gender, phone,
                     disease,
                     address, marry, num_people, live,
                     smoke, alcohol, height_cm, weight_kg, waist_cm,
                     birthdate, hearing_left, hearing_right, vision_snellen,
                     date_assessed)
                VALUES
                    (%s, %s,
                     %s, %s, %s, %s, %s,
                     %s,
                     %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s,
                     NOW())
                """,
                (
                    hn, gcn,
                    first_name, surname, age, gender, phone,
                    disease,
                    address, marry, num_ppl, live,
                    smoke, alcohol, height_cm, weight_kg, waist_cm,
                    birthdate, hearing_left, hearing_right, vision_snellen,
                ),
            )

        conn.commit()
        conn.close()

        # -------- 3) เช็คว่ากดปุ่มไป step ไหน --------
        goto = request.form.get("goto_step")

        if goto == "1":
            return redirect(url_for("assess_session", hn=hn, gcn=gcn))
        elif goto == "3":
            return redirect(url_for("affect_step", hn=hn, gcn=gcn))
        else:
            return redirect(url_for("mmse_next", hn=hn, gcn=gcn))

    # ================== GET: แค่เปิดหน้า step 1 ==================
    conn.close()

    # แยกโรคประจำตัว + โรคอื่น ๆ สำหรับแสดงบนฟอร์ม
    disease_list = []
    disease_other = ""
    if patient and patient.get("disease"):
        parts = patient["disease"].split(",")
        for p in parts:
            p = p.strip()
            if p.startswith("อื่น ๆ:") or p.startswith("อื่น ๆ:"):
                # รองรับทั้ง "อื่น ๆ:xxx" และ "อื่น ๆ: xxx"
                disease_other = p.split(":", 1)[1].strip()
            elif p:
                disease_list.append(p)

    return render_template(
        "assess_session.html",
        hn=hn,
        gcn=gcn,
        patient=patient,
        disease_list=disease_list,
        disease_other=disease_other,
        step=1,
    )




# ------------------- Run App -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

