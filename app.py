from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from flask import request, render_template
import mysql.connector
from mysql.connector import Error
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify


def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",       # หรือ "127.0.0.1"
            user="root",            # 👈 ชื่อผู้ใช้ MySQL ของคุณ
            password="Kantiya203_",            # 👈 ถ้ามีรหัสผ่านให้ใส่ที่นี่
            database="cga_system"   # 👈 ชื่อ database ที่คุณสร้างใน MySQL Workbench
        )
        print("✅ Database connected successfully")
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Database connection error: {err}")
        return None

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


app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # ใช้กับ flash และ session

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
    patient_id = get_patient_id_by_hn_gcn(hn, gcn)

    if request.method == "POST":
        # 1) คะแนนรวม + ระดับการศึกษา (เหมือนเดิม)
        mmse_total = int(request.form.get("total_score", 0))
        edu = request.form.get("edu", "")

        # 2) ดึงคำตอบรายข้อจากฟอร์ม
        q1_1 = int(request.form.get("q1_1", 0))
        q1_2 = int(request.form.get("q1_2", 0))
        q1_3 = int(request.form.get("q1_3", 0))
        q1_4 = int(request.form.get("q1_4", 0))
        q1_5 = int(request.form.get("q1_5", 0))

        q2_1 = int(request.form.get("q2_1", 0))
        q2_2 = int(request.form.get("q2_2", 0))
        q2_3 = int(request.form.get("q2_3", 0))
        q2_4 = int(request.form.get("q2_4", 0))
        q2_5 = int(request.form.get("q2_5", 0))

        q3   = int(request.form.get("q3", 0))
        q4_1 = int(request.form.get("q4_1", 0))
        q4_2 = int(request.form.get("q4_2", 0))
        q5   = int(request.form.get("q5", 0))
        q6   = int(request.form.get("q6", 0))
        q7   = int(request.form.get("q7", 0))
        q8   = int(request.form.get("q8", 0))
        q9   = int(request.form.get("q9", 0))
        q10  = int(request.form.get("q10", 0))
        q11  = int(request.form.get("q11", 0))

        # (ถ้า total_score ถูก JS คำนวณมาแล้ว ก็ใช้ mmse_total ตามนั้นได้เลย
        # ถ้าอยากเช็กซ้ำก็คำนวณเองอีกรอบได้)
        print(f"➡️ MMSE POST: total={mmse_total}, edu={edu}")

        # 3) บันทึกลงตาราง assessment_mmse (ถ้ามี patient_id)
        if patient_id:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)

            # ตรวจว่ามี record เดิมหรือยัง
            cur.execute("SELECT id FROM assessment_mmse WHERE patient_id=%s", (patient_id,))
            row = cur.fetchone()

            if row:
                # UPDATE
                cur.execute("""
                    UPDATE assessment_mmse
                    SET q1_1=%s, q1_2=%s, q1_3=%s, q1_4=%s, q1_5=%s,
                        q2_1=%s, q2_2=%s, q2_3=%s, q2_4=%s, q2_5=%s,
                        q3=%s, q4_1=%s, q4_2=%s,
                        q5=%s, q6=%s, q7=%s, q8=%s, q9=%s, q10=%s, q11=%s,
                        total_score=%s
                    WHERE id=%s
                """, (q1_1, q1_2, q1_3, q1_4, q1_5,
                      q2_1, q2_2, q2_3, q2_4, q2_5,
                      q3, q4_1, q4_2,
                      q5, q6, q7, q8, q9, q10, q11,
                      mmse_total, row["id"]))
            else:
                # INSERT
                cur.execute("""
                    INSERT INTO assessment_mmse
                    (patient_id, q1_1, q1_2, q1_3, q1_4, q1_5,
                     q2_1, q2_2, q2_3, q2_4, q2_5,
                     q3, q4_1, q4_2,
                     q5, q6, q7, q8, q9, q10, q11,
                     total_score)
                    VALUES (%s,%s,%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,
                            %s,%s,%s,
                            %s,%s,%s,%s,%s,%s,%s,
                            %s)
                """, (patient_id,
                      q1_1, q1_2, q1_3, q1_4, q1_5,
                      q2_1, q2_2, q2_3, q2_4, q2_5,
                      q3, q4_1, q4_2,
                      q5, q6, q7, q8, q9, q10, q11,
                      mmse_total))

            conn.commit()
            cur.close()
            conn.close()

            # อัปเดตคะแนนรวมใน patient_history ให้ตรงกับ mmse_total
            conn2 = get_db_connection()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE patient_history SET mmse=%s WHERE id=%s",
                         (mmse_total, patient_id))
            conn2.commit()
            cur2.close()
            conn2.close()

        # 4) ส่งต่อไปหน้า affect_step เหมือนเดิม
        return redirect(url_for("affect_step",
                                hn=hn,
                                gcn=gcn,
                                mmse=mmse_total,
                                edu=edu))

    # GET: แสดงหน้าแบบประเมิน MMSE ปกติ
    return render_template("mmse.html", hn=hn, gcn=gcn)



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

    return render_template(
        "dashboard.html",
        kpis=kpis,  # ✅ ส่ง object kpis
        bar_labels=bar_labels,
        bar_values=bar_values,
        risk=risk
    )

# (ต้องมีบรรทัดนี้อยู่ด้านบนของไฟล์ app.py)
# from flask import render_template

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

    today_th = datetime.now().strftime("%d %b %Y")

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
    # 1. ดึงข้อมูลผู้ป่วย
    show_name = "ผู้ป่วย"
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name FROM patients WHERE hn = %s", (hn,))
        res = cursor.fetchone()
        if res and 'name' in res:
            show_name = res['name']
        conn.close()
    except:
        pass

    # 2. คำนวณวันที่ไทย (นี่คือจุดสำคัญ)
    now = datetime.now()
    thai_months = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    # ✅ ตั้งชื่อตัวแปรว่า thaidate_str
    thaidate_str = f"{now.day} {thai_months[now.month - 1]} {now.year + 543}"

    # 3. เตรียมข้อมูลอื่นๆ
    patient_data = { "name": show_name, "hn": hn, "gcn": gcn }
    ai_summary = {
        "cognitive": "มีภาวะสมองเสื่อมเล็กน้อย",
        "depression": "ไม่พบภาวะซึมเศร้า",
        "suicide_risk": "ไม่พบความเสี่ยง",
        "recommendations": ["ควรทำกิจกรรมกระตุ้นสมอง"]
    }
    
    # 4. ส่งไปหน้าเว็บ (ส่ง thaidate_str ไปใส่ในช่อง thaidate)
    return render_template("ai_analysis.html", 
                           patient=patient_data, 
                           ai_summary=ai_summary, 
                           thaidate=thaidate_str)

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
    
    if request.method == "POST":
        # --- ส่วนที่ 1: รับคะแนนใหม่ (TGDS, SRA) ---
        # ⚠️ หมายเหตุ: คุณต้องใช้ JavaScript ใน affect.html คำนวณคะแนน
        # แล้วส่งมาใน <input> ที่ชื่อ "tgds_total" และ "sra_total"
        # (ผมใส่ 0 เป็นค่าเริ่มต้น หากยังไม่ได้ทำ JS)
        tgds = int(request.form.get("tgds_total", 0))
        sra = int(request.form.get("sra_total", 0))

        # --- ส่วนที่ 2: รับคะแนนเก่า (MMSE) ที่ซ่อนมาในฟอร์ม ---
        mmse = int(request.form.get("mmse", 0))
        edu = request.form.get("edu", "")

        print(f"➡️ Affect Step POST: MMSE={mmse}, TGDS={tgds}, SRA={sra}")
        # --- เริ่มโค้ดคำนวณ TGDS-15 ---
        tgds_score = 0
        
        # ข้อที่ 'ไม่ใช่' (no) ได้ 1 คะแนน
        no_points_questions = [1, 5, 7, 11, 13]
        # ข้อที่ 'ใช่' (yes) ได้ 1 คะแนน
        yes_points_questions = [2, 3, 4, 6, 8, 9, 10, 12, 14, 15]

        # วนลูปคำนวณคะแนน
        for i in no_points_questions:
            answer = request.form.get(f'tgds_{i}') # เช่น รับค่า 'no'
            if answer == 'no':
                tgds_score += 1
        
        for i in yes_points_questions:
            answer = request.form.get(f'tgds_{i}') # เช่น รับค่า 'yes'
            if answer == 'yes':
                tgds_score += 1
        
        # --- จบโค้ดคำนวณ TGDS-15 ---
        # --- ส่วนที่ 3: ส่งต่อคะแนนทั้งหมดไปที่ summary ---
        # นี่คือจุดที่แก้ปัญหา 0/30 ครับ
        return redirect(url_for("cga_summary", 
                                hn=hn, gcn=gcn, 
                                mmse=mmse, 
                                edu=edu, 
                                tgds=tgds_score, 
                                sra=sra))

    # --- ส่วนของ GET (เมื่อโหลดหน้าครั้งแรก) ---
    # 4. รับคะแนนที่ส่งมาจาก mmse_step
    mmse = request.args.get("mmse", 0)
    edu = request.args.get("edu", "")
    
    # 5. ส่งต่อไปให้ template เพื่อเอาไปซ่อนใน hidden field
    return render_template("affect.html", 
                           hn=hn, gcn=gcn, 
                           mmse_current=mmse, # 👈 ส่งค่า mmse ไปให้ .html
                           edu_current=edu)   # 👈 ส่งค่า edu ไปให้ .html

    
   
   # ------------------- จัดการข้อมูลผู้ป่วย -------------------
@app.route("/patients")
def patient_list():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    search = request.args.get("search", "")
    if search:
        cur.execute("SELECT * FROM patient_history WHERE name LIKE %s OR hn LIKE %s OR gcn LIKE %s",
                    (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cur.execute("SELECT * FROM patient_history ORDER BY id DESC")
    patients = cur.fetchall()
    conn.close()
    return render_template("patients.html", patients=patients, search=search)


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

    if request.method == "POST":
        # ===== รับค่าจากฟอร์ม =====
        name = request.form["name"]
        hn = request.form["hn"]
        gcn = request.form["gcn"]
        age = request.form["age"]
        gender = request.form["gender"]
        disease = request.form["disease"]
        risk_level = request.form["risk_level"]

        # คะแนนประเมิน (ถ้าไม่ได้ส่งมาให้ใช้ 0)
        mmse = request.form.get("mmse", 0) or 0
        tgds = request.form.get("tgds", 0) or 0
        sra  = request.form.get("sra", 0) or 0

        # แปลงเป็น int เผื่อส่งมาเป็น string ว่าง
        mmse = int(mmse)
        tgds = int(tgds)
        sra  = int(sra)

        # ===== อัปเดตลงฐานข้อมูล =====
        cur.execute("""
            UPDATE patient_history 
            SET name=%s, hn=%s, gcn=%s, age=%s, gender=%s, disease=%s,
                risk_level=%s, mmse=%s, tgds=%s, sra=%s
            WHERE id=%s
        """, (name, hn, gcn, age, gender, disease,
              risk_level, mmse, tgds, sra, id))

        conn.commit()
        conn.close()
        flash("แก้ไขข้อมูลสำเร็จ", "success")
        return redirect(url_for("patient_list"))

    # ===== กรณีเป็น GET (แค่เปิดฟอร์ม) ต้องมี return ตรงนี้ =====
    conn.close()
    return render_template("patient_form.html", patient=patient, mode="edit")


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

    # 1) ดึงข้อมูลผู้ป่วยหลัก
    cur.execute("SELECT * FROM patient_history WHERE id = %s", (id,))
    patient = cur.fetchone()

    if not patient:
        conn.close()
        flash("ไม่พบข้อมูลผู้ป่วย", "error")
        return redirect(url_for("patient_list"))

    hn = patient["hn"]
    gcn = patient["gcn"]

    # 2) ดึงรายละเอียด MMSE
    cur.execute("SELECT * FROM assessment_mmse WHERE patient_id = %s", (id,))
    mmse_detail = cur.fetchone()

    # 3) ถ้ามีตาราง TGDS / SRA แยก ให้ดึงเพิ่มตรงนี้
    # (ชื่อ table / column ปรับให้ตรงของคุณเอง)
    try:
        cur.execute("SELECT * FROM assessment_tgds WHERE patient_id = %s", (id,))
        tgds_detail = cur.fetchone()
    except:
        tgds_detail = None

    try:
        cur.execute("SELECT * FROM assessment_sra WHERE patient_id = %s", (id,))
        sra_detail = cur.fetchone()
    except:
        sra_detail = None

    # 4) ดึง note จาก summary (assessment_notes)
    cur.execute("""
        SELECT note, created_at 
        FROM assessment_notes 
        WHERE hn = %s AND gcn = %s 
        ORDER BY created_at DESC
    """, (hn, gcn))
    notes = cur.fetchall()

    conn.close()

    return render_template(
        "patient_history.html",
        patient=patient,
        mmse_detail=mmse_detail,
        tgds_detail=tgds_detail,
        sra_detail=sra_detail,
        notes=notes,
    )


@app.route("/assess/<hn>/<gcn>", methods=["GET", "POST"])
def assess_session(hn, gcn):
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        surname = request.form.get("surname", "").strip()
        age = request.form.get("age", "").strip()
        gender = request.form.get("gender")

        if age == "":
            age = 0

        full_name = f"{name} {surname}".strip()
        if not full_name:
            full_name = "ไม่ระบุชื่อ"

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # 1) เช็คว่ามีคนนี้อยู่แล้วไหม (ตาม HN+GCN)
        cur.execute(
            "SELECT id FROM patient_history WHERE hn = %s AND gcn = %s",
            (hn, gcn)
        )
        existing = cur.fetchone()

        if existing:
            # 2) ถ้ามีอยู่แล้ว → อัปเดตข้อมูล ไม่ต้องสร้างแถวใหม่
            cur.execute("""
                UPDATE patient_history
                SET name=%s, age=%s, gender=%s
                WHERE id=%s
            """, (full_name, age, gender, existing["id"]))
        else:
            # 3) ถ้าไม่มี → INSERT ใหม่เหมือนเดิม
            cur.execute("""
                INSERT INTO patient_history (hn, gcn, name, age, gender)
                VALUES (%s, %s, %s, %s, %s)
            """, (hn, gcn, full_name, age, gender))

        conn.commit()
        conn.close()

        return redirect(url_for("mmse_next", hn=hn, gcn=gcn))

    return render_template("assess_session.html", hn=hn, gcn=gcn)




# ------------------- Run App -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

