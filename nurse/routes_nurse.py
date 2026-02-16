from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Optional, Tuple, List
import mysql.connector
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from mysql.connector import Error  # type: ignore
from db.db import get_db_connection, get_supabase_client
from werkzeug.exceptions import Forbidden
from utils.debug_logger import log_supabase_payload # Import Debug Logger
from ml.hmm_predictor import predictor # 🟢 Import AI Predictor

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

# Inject user into all templates
@nurse_bp.context_processor
def inject_user():
    return dict(user=session.get("full_name") or session.get("username"))

# -------------------------
# Auth guard
# -------------------------
def _require_nurse():
    role = session.get("role")
    user_id = session.get("user_id")
    if not user_id:
        flash("กรุณาเข้าสู่ระบบก่อน", "warning")
        return False
    if role != "nurse":
        raise Forbidden("You do not have permission to access this resource.")
    return True

# -------------------------
# DB introspection helpers
# -------------------------
def safe_supabase_sync(table, data, method='upsert', conflict_col='hn') -> Tuple[bool, str]:
    """
    ระบบส่งข้อมูลขึ้น Supabase แบบอัจฉริยะ 
    หากคอลัมน์ไหนไม่มีใน Cloud จะทำการข้ามและพยายามส่งใหม่จนสำเร็จ
    คืนค่า (is_success, message)
    """
    # 🐛 DEBUG HOOK: Log payload before sending
    try:
        log_supabase_payload(table, data, method)
    except Exception as e:
        print(f"⚠️ Logger Error: {e}")

    try:
        supabase = get_supabase_client()
    except Exception as e:
        return False, f"เชื่อมต่อ Cloud ไม่ได้: {e}"

    attempt_data = data.copy()
    last_error = ""
    
    for i in range(10):
        try:
            if method == 'upsert':
                res = supabase.table(table).upsert(attempt_data, on_conflict=conflict_col).execute()
            else:
                res = supabase.table(table).insert(attempt_data).execute()
            return True, "Success"
        except Exception as e:
            err_msg = str(e)
            last_error = err_msg
            # ถ้า Error เพราะไม่มี Column ใน Cloud ให้ลองลบ Column นั้นออกแล้วส่งใหม่
            if "Could not find the '" in err_msg and "' column" in err_msg:
                try:
                    col_name = err_msg.split("Could not find the '")[1].split("' column")[0]
                    if col_name in attempt_data:
                        print(f"DEBUG: [Safe Sync] Skipping missing column '{col_name}' on table '{table}'")
                        del attempt_data[col_name]
                        continue
                except: pass
            
            print(f"DEBUG: [Safe Sync] ERROR on table '{table}':", e)
            return False, err_msg
            
    return False, f"พยายามส่งหลายครั้งแล้วไม่สำเร็จ: {last_error}"

def _get_val(row: dict, key: str, default=None):
    if not row:
        return default
    for k, v in row.items():
        if k.lower() == key.lower():
            return v
    return default

def _get_assess_data(conn, header_id):
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # ลองหาจาก cga_id ก่อน
        cur.execute("""
            SELECT h.id, h.encounter_id, h.session_id, e.patient_id 
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            WHERE h.id = %s
        """, (header_id,))
        ids = cur.fetchone()
        
        # ถ้าไม่เจอ ลองหาโดยมองว่า header_id คือ encounter_id (กรณีมาจากหน้าประวัติ)
        if not ids:
            cur.execute("""
                SELECT h.id, h.encounter_id, h.session_id, e.patient_id 
                FROM cga_headers h
                JOIN encounters e ON e.id = h.encounter_id
                WHERE h.encounter_id = %s
                ORDER BY h.id DESC LIMIT 1
            """, (header_id,))
            ids = cur.fetchone()

        if not ids:
            return {"hn": "N/A", "gcn": "N/A", "patient_id": None, "session_id": None}
        
        p_id = ids["patient_id"]
        sess_id = ids["session_id"]
        actual_header_id = ids["id"]
        actual_encounter_id = ids["encounter_id"]
        
        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_row = cur.fetchone()
        if not p_row:
            return {"hn": "HN -", "gcn": "---"}
        
        bd_col = "birth_date" if "birth_date" in p_row else ("birthdate" if "birthdate" in p_row else None)
        sex_col = "gender" if "gender" in p_row else ("sex" if "sex" in p_row else None)
        addr_col = "address" if "address" in p_row else ("address_text" if "address_text" in p_row else None)
        age_col = "age_year" if "age_year" in p_row else ("age" if "age" in p_row else None)

        hn_val = p_row.get("hn")
        gcn_val = p_row.get("gcn")
        
        if hn_val and str(hn_val).startswith("TMP"):
            try:
                supabase = get_supabase_client()
                sb_res = supabase.table("patients").select("hn").execute()
                max_num = 0
                pattern = re.compile(r'^HN(\d+)$', re.IGNORECASE)
                
                for r in sb_res.data:
                    if r.get('hn'):
                        m = pattern.match(str(r['hn']))
                        if m:
                            val = int(m.group(1))
                            if val < 1000000 and val > max_num:
                                max_num = val
                
                cur.execute("SELECT hn FROM patients WHERE hn LIKE 'HN%'")
                for r in cur.fetchall():
                    m = pattern.match(str(r['hn']))
                    if m:
                        val = int(m.group(1))
                        if val < 1000000 and val > max_num:
                            max_num = val
                
                hn_display = f"HN{(max_num + 1):03d}"
                cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
                next_gcn = cur.fetchone()['c'] + 1
                gcn_display = f"{next_gcn:03d}"
            except Exception as e:
                print("Preview ID Error:", e)
                hn_display = "HN ---"
                gcn_display = "---"
        else:
            if hn_val:
                clean_hn = str(hn_val).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    hn_display = f"HN{clean_hn.zfill(3)}"
                else:
                    hn_display = str(hn_val)
            else:
                hn_display = "HN -"
            
            gcn_display = str(gcn_val).zfill(3) if gcn_val else "---"

        res = {
            "hn": hn_display,
            "gcn": gcn_display,
            "full_name": p_row.get("full_name"),
            "birth_date": p_row.get(bd_col) if bd_col else None,
            "gender": p_row.get(sex_col) if sex_col else None,
            "address": p_row.get(addr_col) if addr_col else None,
            "phone": p_row.get("phone"),
            "age_year": p_row.get(age_col) if age_col else None,
            "gender": p_row.get("gender"),
            "patient_id": p_id,
            "session_id": sess_id,
            "encounter_id": actual_encounter_id,
            "header_id": actual_header_id
        }

        if sess_id:
            cur.execute("SELECT instrument, answer_text FROM assessment_answers WHERE session_id=%s", (sess_id,))
            for r in cur.fetchall():
                txt = r['answer_text']
                if r['instrument'] == 'basic' and ':' in txt:
                    k, v = txt.split(':', 1)
                    res[k] = v
                elif r['instrument'] == 'mmse_edu':
                    res['edu'] = txt
        
        addr_fields = ['house_no', 'moo', 'subdistrict', 'district', 'province', 'postal_code', 'caregiver_relation', 'caregiver_name', 'emergency_phone']
        for af in addr_fields:
            if af not in res:
                res[af] = ""
        return res
    except Exception as e: 
        print("Error in _get_assess_data:", e)
        return {"hn": "N/A", "gcn": "N/A"}
    finally:
        cur.close()

def _get_answers(conn, header_id, instrument):
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute(f"SELECT id FROM assessment_{instrument} WHERE cga_id = %s", (header_id,))
        h = cur.fetchone()
        if not h:
            return {}
        table = f"assessment_{instrument}_items"
        cur.execute(f"SHOW COLUMNS FROM {table}")
        cols = {r['Field'].lower() for r in cur.fetchall()}
        val_col = "answer" if "answer" in cols else ("answer_text" if "answer_text" in cols else "score")
        cur.execute(f"SELECT question_no, score, {val_col} as val FROM {table} WHERE {instrument}_id = %s", (h['id'],))
        return {r['question_no']: r for r in cur.fetchall()}
    except Exception as e:
        print(f"Error in _get_answers for {instrument}:", e)
        return {}
    finally:
        cur.close()

# -------------------------
# Routes
# -------------------------
@nurse_bp.route("/dashboard", endpoint="dashboard")
def dashboard():
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    kpis = {"today": 0, "week": 0, "month": 0, "total": 0}
    recent_patients = []
    try:
        # 🟢 เปลี่ยนมาใช้ cga_records เพื่อให้ตัวเลขตรงกับหน้ารายงาน
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE assessed_date = CURDATE()")
        kpis["today"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE YEARWEEK(assessed_date, 1) = YEARWEEK(CURDATE(), 1)")
        kpis["week"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE MONTH(assessed_date) = MONTH(CURDATE()) AND YEAR(assessed_date) = YEAR(CURDATE())")
        kpis["month"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records")
        kpis["total"] = cur.fetchone()["c"]

        # 🟢 ดึงผู้ป่วยล่าสุด 5 รายการจาก cga_records โดยตรง
        cur.execute("""
            SELECT 
                encounter_id as header_id, 
                hn, 
                full_name, 
                mmse_score, 
                tgds_score, 
                created_at, 
                CASE 
                    WHEN (mmse_score <= 15 OR tgds_score >= 10 OR suicide_risk = 'มี') THEN 'high'
                    WHEN (mmse_score <= 23 OR tgds_score >= 7) THEN 'medium'
                    ELSE 'low'
                END as overall_risk
            FROM cga_records 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent_patients = cur.fetchall()
        
        # จัดรูปแบบวันที่ให้ Template ใช้งานได้
        for p in recent_patients:
            if p.get('hn'):
                clean_hn = str(p['hn']).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    p['hn'] = f"HN{clean_hn.zfill(3)}"
    except Exception as e:
        print("Dashboard Error:", e)
    finally:
        cur.close()
        conn.close()
    return render_template("nurse/dashboard.html", kpis=kpis, recent_patients=recent_patients, user=session.get("full_name") or session.get("username"), role="พยาบาล")

@nurse_bp.get("/api/kpis", endpoint="api_kpis")
def api_kpis():
    if not _require_nurse():
        return {"error": "unauthorized"}, 401
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # 🟢 อัปเดตให้ดึงจาก cga_records
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE assessed_date = CURDATE()")
        today = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE YEARWEEK(assessed_date, 1) = YEARWEEK(CURDATE(), 1)")
        week = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records WHERE MONTH(assessed_date) = MONTH(CURDATE()) AND YEAR(assessed_date) = YEAR(CURDATE())")
        month = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_records")
        total = cur.fetchone()["c"]
        return {"today": today, "week": week, "month": month, "total": total}
    except Exception as e:
        print("API KPI Error:", e)
        return {"error": str(e)}, 500
    finally:
        cur.close()
        conn.close()

@nurse_bp.get("/reports", endpoint="reports")
def reports():
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    report_data = {'start_date': start_date, 'end_date': end_date}
    try:
        # 🟢 1. สถิติรวมจาก cga_records
        cur.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN mmse_score <= 23 THEN 1 ELSE 0 END) as mmse_risk, 
                   SUM(CASE WHEN tgds_score >= 7 THEN 1 ELSE 0 END) as tgds_risk
            FROM cga_records
            WHERE assessed_date BETWEEN %s AND %s
        """, (start_date, end_date))
        report_data['ov'] = cur.fetchone()
        
        # 🟢 2. รายชื่อกลุ่มเสี่ยงเร่งด่วนจาก cga_records
        cur.execute("""
            SELECT encounter_id as header_id, hn, full_name, birth_date, mmse_score as mmse, tgds_score as tgds, 
                   CASE WHEN suicide_risk = 'มี' THEN 'yes' ELSE 'no' END as suicide
            FROM cga_records
            WHERE assessed_date BETWEEN %s AND %s
              AND (mmse_score <= 23 OR tgds_score >= 7 OR suicide_risk = 'มี')
            ORDER BY assessed_date DESC LIMIT 30
        """, (start_date, end_date))
        report_data['high_risk'] = cur.fetchall()
        
        # 🟢 เพิ่มการนับสถิติโรคประจำตัว (Diseases)
        cur.execute("""
            SELECT answer_text 
            FROM assessment_answers a
            JOIN assessment_sessions s ON a.session_id = s.id
            JOIN cga_headers h ON s.encounter_id = h.encounter_id
            WHERE a.instrument = 'basic' AND a.answer_text LIKE 'chronicDiseases:%'
              AND h.status IN ('completed','sent_to_doctor') 
              AND DATE(h.created_at) BETWEEN %s AND %s
        """, (start_date, end_date))
        disease_rows = cur.fetchall()
        
        disease_counts = {
            'diabetes': 0, 'hypertension': 0, 'heart': 0, 'kidney': 0, 'cancer': 0
        }
        
        for r in disease_rows:
            # text format: "chronicDiseases:diabetes,hypertension"
            val_part = r['answer_text'].split(':', 1)[1]
            diseases = val_part.split(',')
            for d in diseases:
                d = d.strip()
                if d in disease_counts:
                    disease_counts[d] += 1
        
        report_data['diseases'] = disease_counts

        # 🟢 เพิ่มการคำนวณ BMI Stats
        cur.execute("""
            SELECT s.id,
                   MAX(CASE WHEN a.answer_text LIKE 'weight:%' THEN SUBSTRING_INDEX(a.answer_text, ':', -1) END) as w,
                   MAX(CASE WHEN a.answer_text LIKE 'height:%' THEN SUBSTRING_INDEX(a.answer_text, ':', -1) END) as h
            FROM assessment_answers a
            JOIN assessment_sessions s ON a.session_id = s.id
            JOIN cga_headers h ON s.encounter_id = h.encounter_id
            WHERE a.instrument = 'basic' AND (a.answer_text LIKE 'weight:%' OR a.answer_text LIKE 'height:%')
              AND h.status IN ('completed','sent_to_doctor') 
              AND DATE(h.created_at) BETWEEN %s AND %s
            GROUP BY s.id
        """, (start_date, end_date))
        bmi_rows = cur.fetchall()
        
        bmi_stats = {'underweight': 0, 'normal': 0, 'overweight': 0, 'obese': 0}
        
        for r in bmi_rows:
            try:
                w = float(r['w']) if r['w'] else 0
                h_cm = float(r['h']) if r['h'] else 0
                if w > 0 and h_cm > 0:
                    bmi = w / ((h_cm/100)**2)
                    if bmi < 18.5: bmi_stats['underweight'] += 1
                    elif bmi < 23.0: bmi_stats['normal'] += 1
                    elif bmi < 25.0: bmi_stats['overweight'] += 1
                    else: bmi_stats['obese'] += 1
            except:
                pass
        
        report_data['bmi'] = bmi_stats

    except Exception as e:
        print("Report Error:", e)
        if 'diseases' not in report_data: report_data['diseases'] = {}
        if 'bmi' not in report_data: report_data['bmi'] = {'underweight': 0, 'normal': 0, 'overweight': 0, 'obese': 0}
    finally:
        cur.close()
        conn.close()
    return render_template("nurse/summary_report.html", data=report_data, date=date.today().strftime('%d/%m/%Y'))

@nurse_bp.route("/assess/new", methods=["GET", "POST"], endpoint="assess_new")
def assess_new():
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        return assess_create()
    return render_template("nurse/assess_new.html")

@nurse_bp.post("/assess/create", endpoint="assess_create")
def assess_create():
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        import time
        temp_hn = f"TMP-{int(time.time())}"
        cur.execute("INSERT INTO patients (hn, gcn, full_name) VALUES (%s, NULL, 'รอกรอกข้อมูล')", (temp_hn,))
        p_id = cur.lastrowid
        cur.execute("INSERT INTO encounters (patient_id, encounter_date, created_by) VALUES (%s, CURDATE(), %s)", (p_id, session.get("user_id")))
        enc_id = cur.lastrowid
        cur.execute("INSERT INTO assessment_sessions (encounter_id, session_type, created_by) VALUES (%s, 'baseline', %s)", (enc_id, session.get("user_id")))
        sess_id = cur.lastrowid
        cur.execute("INSERT INTO cga_headers (encounter_id, session_id, created_at, status) VALUES (%s, %s, NOW(), 'in_progress')", (enc_id, sess_id))
        conn.commit()
        return redirect(url_for("nurse.assess_session", header_id=cur.lastrowid))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for("nurse.assess_new"))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get('/assess/new_encounter/<string:hn>', endpoint='assess_new_encounter')
def assess_new_encounter(hn: str):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
        
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # 1. หา patient_id จาก HN
        cur.execute("SELECT id, full_name FROM patients WHERE hn = %s", (hn,))
        patient = cur.fetchone()
        if not patient:
            flash(f"ไม่พบข้อมูลผู้ป่วย HN: {hn}", "danger")
            return redirect(url_for('nurse.patients'))
            
        # 2. สร้าง Encounter ใหม่ (วันที่ปัจจุบัน)
        # ตรวจสอบก่อนว่าวันนี้มี Encounter แล้วหรือยัง (กันเบิ้ล)
        cur.execute("SELECT id FROM encounters WHERE patient_id=%s AND encounter_date=CURDATE() AND encounter_type='cga'", (patient['id'],))
        existing_enc = cur.fetchone()
        
        if existing_enc:
            encounter_id = existing_enc['id']
            # เช็คว่ามี Header หรือยัง
            cur.execute("SELECT id FROM cga_headers WHERE encounter_id=%s", (encounter_id,))
            existing_header = cur.fetchone()
            if existing_header:
                flash(f"มีใบประเมินของวันนี้อยู่แล้ว ({patient['full_name']})", "warning")
                return redirect(url_for('nurse.assess_session', header_id=existing_header['id']))
        else:
            cur.execute("""
                INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by)
                VALUES (%s, CURDATE(), 'cga', %s)
            """, (patient['id'], session.get('user_id')))
            encounter_id = cur.lastrowid
        
        # 3. สร้าง CGA Header ใหม่ (ถ้ายังไม่มี)
        cur.execute("""
            INSERT INTO cga_headers (encounter_id, assessed_by, status)
            VALUES (%s, %s, 'pending')
        """, (encounter_id, session.get('user_id')))
        header_id = cur.lastrowid
        
        # 4. สร้าง Session ใหม่ (จำเป็นสำหรับการเก็บ Answers)
        cur.execute("""
            INSERT INTO assessment_sessions (encounter_id, session_type, created_by)
            VALUES (%s, 'baseline', %s)
        """, (encounter_id, session.get('user_id')))
        new_session_id = cur.lastrowid
        
        # 5. [Auto-fill] ดึงข้อมูลพื้นฐานจากใบประเมินล่าสุดมาใส่ให้ (Clone Basic Info)
        # หา session_id ล่าสุดก่อนหน้านี้ของผู้ป่วยคนนี้
        cur.execute("""
            SELECT s.id 
            FROM assessment_sessions s
            JOIN encounters e ON s.encounter_id = e.id
            WHERE e.patient_id = %s AND s.id != %s
            ORDER BY s.created_at DESC LIMIT 1
        """, (patient['id'], new_session_id))
        last_session = cur.fetchone()
        
        if last_session:
            last_sess_id = last_session['id']
            # รายการ Field ที่ต้องการ Clone (ที่อยู่, ผู้ดูแล, สถานะ, การศึกษา, โรคประจำตัว)
            clone_fields = [
                'caregiver_name', 'caregiver_relation', 'emergency_phone', # ผู้ดูแล
                'house_no', 'moo', 'subdistrict', 'district', 'province', 'postal_code', # ที่อยู่
                'marry', 'live', 'education', # สถานะทางสังคม
                'chronicDiseases' # โรคประจำตัว
            ]
            
            # ดึงคำตอบเดิมมา
            cur.execute("""
                SELECT instrument, question_no, answer_text 
                FROM assessment_answers 
                WHERE session_id = %s AND instrument = 'basic'
            """, (last_sess_id,))
            old_answers = cur.fetchall()
            
            # วนลูป Insert ลง Session ใหม่
            for ans in old_answers:
                txt = ans['answer_text']
                # เช็คว่าเป็น Field ที่เราอยากได้ไหม (Format: key:value)
                if ':' in txt:
                    key = txt.split(':', 1)[0]
                    if key in clone_fields or key == 'chronicDiseases': # chronicDiseases อาจมาในรูปแบบ key:value หรือ csv
                         cur.execute("""
                            INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text)
                            VALUES (%s, %s, %s, %s)
                        """, (new_session_id, ans['instrument'], ans['question_no'], txt))
        
        conn.commit()
        
        flash(f"เริ่มการประเมินใหม่สำหรับคุณ {patient['full_name']} เรียบร้อยแล้ว (ดึงข้อมูลเดิมมาให้บางส่วน)", "success")
        return redirect(url_for('nurse.assess_session', header_id=header_id))
        
    except Exception as e:
        conn.rollback()
        flash(f"เกิดข้อผิดพลาดในการสร้างการประเมินใหม่: {e}", "danger")
        return redirect(url_for('nurse.patients'))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get("/assess/session/<int:header_id>", endpoint="assess_session")
def assess_session(header_id: int):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    assess = _get_assess_data(conn, header_id)
    conn.close()
    return render_template("nurse/assess_session.html", assess=assess, hn=assess.get("hn"), gcn=assess.get("gcn"), header_id=header_id)

@nurse_bp.post('/assess/step1/save/<int:header_id>', endpoint='assess_step1_save')
def assess_step1_save(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    f = request.form
    full_name = f"{f.get('name','')} {f.get('surname','')}".strip()
    
    # Re-construct readable address for patient table
    readable_addr = []
    if f.get('house_no'): readable_addr.append(f"เลขที่ {f['house_no']}")
    if f.get('moo'): readable_addr.append(f"หมู่ {f['moo']}")
    if f.get('subdistrict'): readable_addr.append(f"ต. {f['subdistrict']}")
    if f.get('district'): readable_addr.append(f"อ. {f['district']}")
    if f.get('province'): readable_addr.append(f"จ. {f['province']}")
    if f.get('postal_code'): readable_addr.append(f"{f['postal_code']}")
    final_readable_addr = " ".join(readable_addr)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        data = _get_assess_data(conn, header_id)
        p_id = data.get("patient_id")
        sess_id = data.get("session_id")
        
        # Update Patients Table (Local)
        cur.execute("UPDATE patients SET full_name=%s, birth_date=%s, gender=%s, phone=%s, address=%s WHERE id=%s",
                    (full_name, f.get('birthdate') or None, f.get('gender'), f.get('phone'), final_readable_addr, p_id))
        
        if sess_id:
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (sess_id,))
            fields = ['marry', 'live', 'smoke', 'alcohol', 'hearing_left', 'hearing_right', 'visionTest', 'vision_left', 'vision_right', 'height', 'weight', 'waist', 'otherDisease', 'age', 'house_no', 'moo', 'subdistrict', 'district', 'province', 'postal_code', 'hearing_left_detail', 'hearing_right_detail', 'emergency_phone', 'caregiver_name', 'caregiver_relation', 'alcohol_daily_amount']
            for k in fields:
                if f.get(k):
                    cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'basic', 0, %s)", (sess_id, f"{k}:{f.get(k)}"))
            
            d = f.getlist('chronicDiseases')
            if d:
                cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'basic', 0, %s)", (sess_id, f"chronicDiseases:{','.join(d)}"))
        
        conn.commit()

        # 🟢 Sync ข้อมูลผู้ดูแล/ที่อยู่ ลง cga_records ทันที
        _sync_to_cga_records(header_id, conn, cur)

        if f.get('next_url'):
            return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_session', header_id=header_id))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get('/assess/mmse/<int:header_id>', endpoint='assess_mmse')
def assess_mmse(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    data = _get_assess_data(conn, header_id)
    answers = _get_answers(conn, header_id, 'mmse')
    
    # เช็คประวัติการประเมินล่าสุดเพื่อดูว่าเป็นเคสประเมินซ้ำภายใน 2 เดือนหรือไม่
    is_repeat_2m = False
    try:
        cur.execute("""
            SELECT h.created_at 
            FROM cga_headers h
            JOIN encounters e ON h.encounter_id = e.id
            WHERE e.patient_id = %s AND h.id < %s AND h.status = 'completed'
            ORDER BY h.created_at DESC LIMIT 1
        """, (data.get('patient_id'), header_id))
        last_h = cur.fetchone()
        if last_h:
            delta = datetime.now() - last_h['created_at']
            if delta.days <= 60:
                is_repeat_2m = True
    except Exception as e:
        print("Check repeat MMSE error:", e)

    cur.close()
    conn.close()
    return render_template('nurse/mmse.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), assess=data, answers=answers, is_repeat_2m=is_repeat_2m)

@nurse_bp.post('/assess/mmse/save/<int:header_id>', endpoint='assess_mmse_save')
def assess_mmse_save(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    f = request.form
    try:
        # 🟢 1. หา cga_id ที่แท้จริง (ป้องกัน Error 1452)
        actual_cga_id = header_id
        cur.execute("SELECT id FROM cga_headers WHERE id = %s", (header_id,))
        if not cur.fetchone():
            # ถ้าหาไม่เจอ แสดงว่า header_id ที่ส่งมาอาจเป็น encounter_id (จากหน้าประวัติ/รายงาน)
            cur.execute("SELECT id FROM cga_headers WHERE encounter_id = %s", (header_id,))
            h_row = cur.fetchone()
            if h_row:
                actual_cga_id = h_row['id']
            else:
                # ถ้ายังไม่มีเลย ให้สร้างใหม่ผูกกับ encounter_id นั้น
                cur.execute("INSERT INTO cga_headers (encounter_id, status) VALUES (%s, 'in_progress')", (header_id,))
                conn.commit()
                actual_cga_id = cur.lastrowid

        # ดึงระดับการศึกษา
        edu = f.get('edu', '3')
        is_no_edu = (edu == '1')

        cur.execute("INSERT INTO assessment_mmse (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (actual_cga_id,))
        cur.execute("SELECT id FROM assessment_mmse WHERE cga_id = %s", (actual_cga_id,))
        mm_id = cur.fetchone()['id']
        cur.execute("DELETE FROM assessment_mmse_items WHERE mmse_id = %s", (mm_id,))
        
        total_score = 0
        # (ส่วนของการวนลูปบันทึกคะแนนเหมือนเดิม แต่ใช้ actual_cga_id)
        normal_qs = ['1.1', '1.2', '1.3', '1.4', '1.5', '2.1', '2.2', '2.3', '2.4', '2.5', '3', '5', '6', '7', '8', '11']
        for q_no in normal_qs:
            val = f.get(f'q{q_no}', '0')
            score = int(val) if val.isdigit() else 0
            cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, q_no, score))
            total_score += score

        if not is_no_edu:
            q41_val = f.get('q4.1')
            q42_val = f.get('q4.2')
            s4_score = 0
            if q41_val is not None:
                s4_score = int(q41_val)
                cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, '4.1', s4_score))
            elif q42_val is not None:
                s4_score = int(q42_val)
                cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, '4.2', s4_score))
            total_score += s4_score

            for q_no in ['9', '10']:
                val = f.get(f'q{q_no}', '0')
                score = int(val) if val.isdigit() else 0
                cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, q_no, score))
                total_score += score
        
        cur.execute("UPDATE assessment_mmse SET total_score=%s WHERE id=%s", (total_score, mm_id))
        
        sess_id = _get_assess_data(conn, actual_cga_id).get('session_id')
        if sess_id and f.get('edu'):
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='mmse_edu'", (sess_id,))
            cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'mmse_edu', 0, %s)", (sess_id, f.get('edu')))
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='basic' AND answer_text LIKE 'education:%%'", (sess_id,))
            cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'basic', 0, %s)", (sess_id, f"education:{f.get('edu')}"))
        
        conn.commit()
        if f.get('next_url'):
            return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_tgds', header_id=actual_cga_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get('/assess/tgds/<int:header_id>', endpoint='assess_tgds')
def assess_tgds(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    data = _get_assess_data(conn, header_id)
    tg_raw = _get_answers(conn, header_id, 'tgds')
    other = {}
    try:
        sess_id = data.get('session_id')
        if sess_id:
            cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s", (sess_id,))
            for r in cur.fetchall():
                inst, q_no, val = r['instrument'], r['question_no'], r['answer_text']
                if inst in ['incontinence','sleepProblems','suicideRisk', 'sleep_problem_detail', 'incontinence_detail']:
                    other[inst] = val
                elif inst == 'depression2Q':
                    other[f"depression2Q_q{q_no}"] = val
                else:
                    other[f"{inst}_{q_no}"] = val
    except:
        pass
    comb = other.copy()
    for q, i in tg_raw.items():
        comb[f"tgds15Answers_{q}"] = 'yes' if i['val'] == 1 else 'no'
    cur.close()
    conn.close()
    # ตรวจสอบว่าเป็น Baseline (ครั้งแรก) หรือไม่? เพื่อใช้กับ 8Q (ข้อ 8 ถามเฉพาะครั้งแรก)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    
    # นับจำนวน Header ก่อนหน้านี้ของผู้ป่วยคนนี้
    cur.execute("""
        SELECT COUNT(*) as c 
        FROM cga_headers h
        JOIN encounters e ON h.encounter_id = e.id
        WHERE e.patient_id = (SELECT patient_id FROM encounters WHERE id = %s)
          AND h.id < %s
    """, (data.get('encounter_id'), header_id))
    count_prev = cur.fetchone()['c']
    is_baseline = (count_prev == 0)
    
    conn.close()

    return render_template('nurse/tgds15.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), assess=data, answers=comb, is_baseline=is_baseline)

@nurse_bp.post('/assess/tgds/save/<int:header_id>', endpoint='assess_tgds_save')
def assess_tgds_save(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    f = request.form
    try:
        # 🟢 1. หา cga_id ที่แท้จริง (ป้องกัน Error 1452)
        actual_cga_id = header_id
        cur.execute("SELECT id FROM cga_headers WHERE id = %s", (header_id,))
        if not cur.fetchone():
            cur.execute("SELECT id FROM cga_headers WHERE encounter_id = %s", (header_id,))
            h_row = cur.fetchone()
            if h_row:
                actual_cga_id = h_row['id']
            else:
                cur.execute("INSERT INTO cga_headers (encounter_id, status) VALUES (%s, 'in_progress')", (header_id,))
                conn.commit()
                actual_cga_id = cur.lastrowid

        cur.execute("INSERT INTO assessment_tgds (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (actual_cga_id,))
        cur.execute("SELECT id FROM assessment_tgds WHERE cga_id = %s", (actual_cga_id,))
        tg_id = cur.fetchone()['id']
        cur.execute("DELETE FROM assessment_tgds_items WHERE tgds_id = %s", (tg_id,))
        
        sess_id = _get_assess_data(conn, actual_cga_id).get('session_id')
        if sess_id:
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument IN ('tgds15Answers','depression2Q','depression8Q','incontinence','sleepProblems','suicideRisk','sleep_problem_detail','incontinence_detail')", (sess_id,))
        
        score = 0
        rev = [1, 5, 7, 11, 13]
        has_suicide_risk = False
        
        # 8Q Calculation
        q8_score = 0
        q8_weights = {1:1, 2:2, 3:4, 4:6, 5:8, 6:9, 7:9, 8:4}
        q3_val = 'no'
        q3_sub_val = 'no'

        for k, v in f.items():
            if k.startswith('tgds15Answers_'):
                q = int(k.split('_')[1])
                is_risk = 1 if (q in rev and v=='no') or (q not in rev and v=='yes') else 0
                score += is_risk
                cur.execute("INSERT INTO assessment_tgds_items (tgds_id, question_no, answer, score) VALUES (%s, %s, %s, %s)", (tg_id, q, (1 if v=='yes' else 0), is_risk))
                if sess_id:
                    cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'tgds15Answers',%s,%s)", (sess_id, q, v))
            elif k.startswith('depression2Q_') and sess_id:
                cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'depression2Q',%s,%s)", (sess_id, (1 if 'q1' in k else 2), v))
            elif k.startswith('depression8Q_') and sess_id:
                # 8Q Logic
                if k == 'depression8Q_3_uncontrollable':
                    q3_sub_val = v
                    cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'depression8Q_sub',3,%s)", (sess_id, v))
                else:
                    q_idx = int(k.split('_')[1])
                    if v == 'yes':
                        has_suicide_risk = True
                        q8_score += q8_weights.get(q_idx, 0)
                        if q_idx == 3: q3_val = 'yes'
                    cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'depression8Q',%s,%s)", (sess_id, q_idx, v))
            elif k in ['incontinence','sleepProblems', 'sleep_problem_detail', 'incontinence_detail'] and sess_id:
                cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,%s,1,%s)", (sess_id, k, v))
        
        # Special Logic for Q3 Sub (Uncontrollable)
        if q3_val == 'yes' and q3_sub_val == 'yes':
            q8_score += 10

        if sess_id:
            sr_val = 'yes' if has_suicide_risk else 'none'
            cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'suicideRisk',1,%s)", (sess_id, sr_val))
        
        cur.execute("UPDATE assessment_tgds SET total_score=%s WHERE id=%s", (score, tg_id))
        
        next_url = f.get('next_url')
        if next_url and 'summary' not in next_url:
            conn.commit()
            return redirect(next_url)

        # 🟢 2. คำนวณความเสี่ยงรวม (Risk Level)
        cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (actual_cga_id,))
        mmse_row = cur.fetchone(); m_score = mmse_row['total_score'] if mmse_row else 0
        risk_lv = 'high' if (m_score <= 15 or score >= 10 or has_suicide_risk) else ('medium' if (m_score <= 23 or score >= 7) else 'low')

        # 3. Finalize IDs and Update Local Header
        cur.execute("UPDATE cga_headers SET status='completed', overall_risk=%s WHERE id=%s", (risk_lv, actual_cga_id))
        
        cur.execute("SELECT h.*, e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (actual_cga_id,))
        h_data = cur.fetchone(); p_id = h_data['patient_id']
        
        # Update 8Q Score to cga_records
        try:
            cur.execute("UPDATE cga_records SET q8_score=%s WHERE encounter_id=%s", (h_data['encounter_id'],))
        except Exception as e:
            print(f"Update 8Q Score Error: {e}")

        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_row = cur.fetchone()
        
        final_hn = p_row['hn']; final_gcn = p_row['gcn']
        max_num = 0; pattern = re.compile(r'^HN(\d+)$', re.IGNORECASE)
        
        if not final_hn or str(final_hn).startswith("TMP"):
            supabase = get_supabase_client()
            sb_res = supabase.table("patients").select("hn").execute()
            for r in sb_res.data:
                if r.get('hn'):
                    m = pattern.match(str(r['hn']))
                    if m:
                        val = int(m.group(1))
                        if val < 1000000 and val > max_num: max_num = val
            
            cur.execute("SELECT hn FROM patients WHERE hn LIKE 'HN%'")
            for r in cur.fetchall():
                m = pattern.match(str(r['hn']))
                if m:
                    val = int(m.group(1))
                    if val < 1000000 and val > max_num: val = val
            
            final_hn = f"HN{(max_num + 1):03d}"
            
        if not final_gcn:
            cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
            final_gcn = f"{(cur.fetchone()['c'] + 1):03d}"
        
        cur.execute("UPDATE patients SET hn=%s, gcn=%s WHERE id=%s", (final_hn, final_gcn, p_id))
        conn.commit()

        # CLOUD SYNC
        sync_errors = []
        try:
            cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
            p_latest = cur.fetchone(); sex_map = {'male': 'ชาย', 'female': 'หญิง'}

            cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (h_data['session_id'],))
            ans_rows = cur.fetchall()
            caregiver_info = {}
            for row in ans_rows:
                txt = row['answer_text']
                if ':' in txt:
                    k, v = txt.split(':', 1)
                    if k in ['caregiver_name', 'caregiver_relation', 'emergency_phone']:
                        caregiver_info[k] = v

            sb_p = {
                "hn": p_latest['hn'], "gcn": str(p_latest['gcn']).zfill(3), 
                "full_name": p_latest['full_name'], "phone": p_latest['phone'], 
                "address": p_latest['address'], "sex": sex_map.get(p_latest['gender'], p_latest['gender']), 
                "birth_date": str(p_latest['birth_date']) if p_latest['birth_date'] else None,
                **caregiver_info 
            }
            safe_supabase_sync("patients", sb_p, method='upsert', conflict_col='hn')
            
            cur.execute("SELECT * FROM encounters WHERE id = %s", (h_data['encounter_id'],))
            enc_raw = cur.fetchone()
            if enc_raw:
                supabase = get_supabase_client()
                sb_p_res = supabase.table("patients").select("id").eq("hn", p_latest['hn']).execute()
                if sb_p_res.data:
                    enc_payload = {
                        "id": enc_raw['id'],
                        "patient_id": sb_p_res.data[0]['id'],
                        "encounter_date": str(enc_raw['encounter_date']),
                        "created_by": enc_raw['created_by']
                    }
                    safe_supabase_sync("encounters", enc_payload, method='upsert', conflict_col='id')

            cga_sb_data = {
                "encounter_id": h_data['encounter_id'], 
                "assessed_by": int(session.get('user_id', 0)), 
                "assessment_date": str(date.today()), 
                "risk_level": risk_lv, 
                "overall_risk": risk_lv, 
                "status": "completed",
                "is_completed": True
            }
            safe_supabase_sync("cga_headers", cga_sb_data, method='upsert', conflict_col='encounter_id')
            
        except Exception as e: 
            print("Sync Error:", e)
            
        _sync_to_cga_records(actual_cga_id, conn, cur)
            
        return redirect(url_for('nurse.assess_summary', header_id=actual_cga_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_tgds', header_id=header_id))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get('/assess/summary/<int:header_id>', endpoint='assess_summary')
def assess_summary(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    data = _get_assess_data(conn, header_id)
    
    # 8Q Logic... (ย้าย m_score, t_score ออกไปคำนวณด้านล่างด้วย real_cga_id)
    
    # ดึงคะแนน 8Q (q8_score) จาก cga_records
    q8_val = 0
    try:
        cur.execute("SELECT q8_score FROM cga_records WHERE encounter_id=%s", (data.get('encounter_id'),))
        q8_row = cur.fetchone()
        if q8_row and q8_row['q8_score'] > 0:
            q8_val = q8_row['q8_score']
        else:
            # Fallback: คำนวณสดจาก assessment_answers
            cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s AND (instrument='depression8Q' OR instrument='depression8Q_sub')", (data.get('session_id'),))
            ans8q = cur.fetchall()
            q8_weights = {1:1, 2:2, 3:4, 4:6, 5:8, 6:9, 7:9, 8:4}
            q3_v = 'no'; q3_s = 'no'
            for r in ans8q:
                if r['instrument'] == 'depression8Q':
                    try:
                        q_idx = int(r['question_no'])
                        if r['answer_text'] == 'yes':
                            q8_val += q8_weights.get(q_idx, 0)
                            if q_idx == 3: q3_v = 'yes'
                    except: pass
                elif r['instrument'] == 'depression8Q_sub':
                    q3_s = r['answer_text']
            if q3_v == 'yes' and q3_s == 'yes':
                q8_val += 10
    except Exception as e:
        print("Summary 8Q Error:", e)
    
    cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='suicideRisk'", (data.get('session_id'),))
    sr_res = cur.fetchone()
    sr_val = sr_res['answer_text'] if sr_res else 'none'
    
    cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='incontinence'", (data.get('session_id'),))
    ir_res = cur.fetchone()
    inc_val = ir_res['answer_text'] if ir_res else 'normal'
    
    cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='sleepProblems'", (data.get('session_id'),))
    sl_res = cur.fetchone()
    sl_val = sl_res['answer_text'] if sl_res else 'normal'

    # ดึงข้อมูลเพิ่มเติมสำหรับหน้า Summary (Depression 2Q, Health Behavior)
    cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s", (data.get('session_id'),))
    all_ans = cur.fetchall()
    
    # ดึงข้อมูลทั้งหมด (Full Info) เพื่อแสดงในหน้าสรุปแบบละเอียด
    full_info = {}
    
    # แปลง key จาก assessment_answers ให้เป็น Dictionary ที่เข้าถึงง่าย
    for r in all_ans:
        inst = r['instrument']
        val = r['answer_text']
        
        if inst == 'basic' and ':' in val:
            k, v = val.split(':', 1)
            full_info[k] = v
        elif inst == 'incontinence':
            full_info['incontinence'] = val
        elif inst == 'incontinence_detail':
            full_info['incontinence_detail'] = val
        elif inst == 'sleepProblems':
            full_info['sleep_problem'] = val
        elif inst == 'sleep_problem_detail':
            full_info['sleep_problem_detail'] = val
        elif inst == 'suicideRisk':
            full_info['suicide_risk'] = val

    # เพิ่มเพศเข้าไปใน full_info
    full_info['gender'] = data.get('gender')

    dep_2q_txt = []
    
    for r in all_ans:
        inst = r['instrument']
        val = r['answer_text']
        if inst == 'depression2Q':
            # แปลง yes/no เป็น มี/ไม่มี
            disp_val = 'มี' if val == 'yes' else 'ไม่มี'
            dep_2q_txt.append(f"Q{r['question_no']}: {disp_val}")

    dep_2q_display = ", ".join(dep_2q_txt) if dep_2q_txt else "-"
    
    # คำนวณ BMI และแปลผล
    try:
        w = float(full_info.get('weight', 0))
        h_cm = float(full_info.get('height', 0))
        if w > 0 and h_cm > 0:
            bmi = w / ((h_cm/100)**2)
            full_info['bmi'] = f"{bmi:.1f}"
            if bmi < 18.5: full_info['bmi_eval'] = 'ผอม'
            elif bmi < 23.0: full_info['bmi_eval'] = 'ปกติ'
            elif bmi < 25.0: full_info['bmi_eval'] = 'ท้วม'
            else: full_info['bmi_eval'] = 'อ้วน'
        else:
            full_info['bmi'] = '-'
            full_info['bmi_eval'] = '-'
    except:
        full_info['bmi'] = '-'
        full_info['bmi_eval'] = '-'

    # ดึงรายละเอียดคำตอบรายข้อ (สำหรับ Modal ดูรายละเอียด)
    mmse_details = {}
    tgds_details = {}
    
    # MMSE Items
    # ตรวจสอบก่อนว่า header_id ที่ส่งมาคือ cga_id จริงๆ หรือเป็น encounter_id (กรณีมาจากหน้าประวัติ)
    real_cga_id = header_id
    cur.execute("SELECT id FROM cga_headers WHERE id = %s", (header_id,))
    if not cur.fetchone():
        # ถ้าหาใน cga_headers ไม่เจอ ให้ลองหาโดยมองว่ามันคือ encounter_id
        cur.execute("SELECT id FROM cga_headers WHERE encounter_id = %s", (header_id,))
        found_h = cur.fetchone()
        if found_h: real_cga_id = found_h['id']

    # 🟢 ดึงคะแนนสรุปจากตารางหลักด้วย real_cga_id
    cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s ORDER BY id DESC LIMIT 1", (real_cga_id,))
    m_row = cur.fetchone()
    m_score = m_row['total_score'] if m_row and m_row['total_score'] is not None else 0
    
    cur.execute("SELECT total_score FROM assessment_tgds WHERE cga_id=%s ORDER BY id DESC LIMIT 1", (real_cga_id,))
    t_row = cur.fetchone()
    t_score = t_row['total_score'] if t_row else 0

    cur.execute("""
        SELECT question_no, score 
        FROM assessment_mmse_items 
        WHERE mmse_id = (SELECT id FROM assessment_mmse WHERE cga_id=%s ORDER BY id DESC LIMIT 1)
    """, (real_cga_id,))
    for r in cur.fetchall():
        # เก็บ question_no เป็น string เพื่อให้ matches กับ keys ใน template (เช่น '1.1', '4.1')
        mmse_details[str(r['question_no'])] = r['score']
        
    # TGDS Items
    cur.execute("""
        SELECT question_no, answer 
        FROM assessment_tgds_items 
        WHERE tgds_id = (SELECT id FROM assessment_tgds WHERE cga_id=%s ORDER BY id DESC LIMIT 1)
    """, (real_cga_id,))
    for r in cur.fetchall():
        tgds_details[r['question_no']] = 'ใช่' if r['answer']==1 else 'ไม่ใช่'

    cur.execute("SELECT status FROM cga_headers WHERE id=%s", (header_id,))
    h_row = cur.fetchone()
    h_status = h_row['status'] if h_row else 'completed'
    
    # ระดับการศึกษา
    # ดึงค่าการศึกษาจาก assessment_answers (instrument='basic', key='education')
    edu = '3' # default
    cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic' AND answer_text LIKE 'education:%%'", (data.get('session_id'),))
    edu_row = cur.fetchone()
    if edu_row:
        edu = edu_row['answer_text'].split(':')[1]

    mmse_total = 30
    mmse_threshold = 22 # default (สูงกว่าประถม cutoff ที่ 22 -> <=22 เสี่ยง)
    
    if edu == '1': # ไม่ได้เรียน/อ่านเขียนไม่ได้
        mmse_total = 23
        mmse_threshold = 14
    elif edu == '2': # ประถม
        mmse_total = 30
        mmse_threshold = 17
    
    # logic: Score <= Threshold คือ "เสี่ยง" (Suspected)
    mmse_risk_status = 'suspected' if m_score <= mmse_threshold else 'normal'
    
    # 🟢 AI HMM Prediction
    ai_result = None
    # ดึง encounter_id จาก data ที่มีอยู่แล้ว
    e_id = data.get('encounter_id')
    p_id = data.get('patient_id')

    try:
        # เตรียมข้อมูล 9 อย่างสำหรับ AI
        chronic_diseases_str = full_info.get('chronicDiseases', '')
        chronic_count = len([d for d in chronic_diseases_str.split(',') if d.strip()]) if chronic_diseases_str else 0
        if full_info.get('otherDisease'):
            chronic_count += 1

        ai_input = {
            "age": full_info.get('age', 60),
            "mmse_score": m_score,
            "tgds_score": t_score,
            "incontinence": inc_val,
            "sleep_problem": sl_val,
            "hearing_left": full_info.get('hearing_left'),
            "vision_left": full_info.get('vision_left'),
            "suicide_risk": sr_val,
            "chronic_count": chronic_count
        }
        ai_result = predictor.predict(ai_input)
        
        # 🟢 เพิ่มรายละเอียดปัจจัยที่ AI พบ
        factors = []
        if m_score <= mmse_threshold: factors.append("สมรรถภาพสมองต่ำกว่าเกณฑ์")
        if t_score >= 7: factors.append("พบภาวะซึมเศร้า")
        if inc_val == 'abnormal': factors.append("มีปัญหาการกลั้นปัสสาวะ")
        if sl_val == 'abnormal': factors.append("มีปัญหาการนอนหลับ")
        if sr_val == 'yes': factors.append("มีความเสี่ยงฆ่าตัวตาย")
        if full_info.get('hearing_left') == 'abnormal' or full_info.get('hearing_right') == 'abnormal': factors.append("พบความผิดปกติของการได้ยิน")
        if chronic_count >= 3: factors.append("มีโรคประจำตัวหลายโรค")
        
        ai_result['factors'] = factors
        print(f"AI Prediction for header {header_id}: {ai_result}")
    except Exception as e:
        print("AI Prediction Error:", e)
        ai_result = {"error": str(e)}

    # ดึงข้อมูล HN และ GCN ล่าสุด
    fresh_p = {"hn": data.get("hn"), "gcn": data.get("gcn")}
    if p_id:
        cur.execute("SELECT hn, gcn FROM patients WHERE id = %s", (p_id,))
        row = cur.fetchone()
        if row: fresh_p = row
    
    cur.close()
    conn.close()
    return render_template('nurse/summary.html', header_id=header_id, hn=fresh_p['hn'], gcn=fresh_p['gcn'], patient=data, date=date.today().strftime('%d/%m/%Y'), user={'name': session.get('full_name')}, mmse_score=m_score, mmse_total=mmse_total, mmse_risk=mmse_risk_status, mmse_threshold=mmse_threshold, tgds_score=t_score, tgds_risk=('normal' if t_score < 7 else 'suspected'), tgds_risk_label=('ปกติ' if t_score < 7 else 'มีภาวะซึมเศร้า'), suicide_risk=sr_val, incontinence=inc_val, sleep=sl_val, status=h_status, dep_2q=dep_2q_display, mmse_details=mmse_details, tgds_details=tgds_details, q8_score=q8_val, full_info=full_info, ai_result=ai_result)

# Helper function to sync data to cga_records (Flat Table)
def _sync_to_cga_records(header_id, conn, cur):
    """
    Rathers all data for a specific CGA header and inserts/updates it into cga_records table.
    Handles both Local and Cloud sync.
    """
    print(f"DEBUG: Starting _sync_to_cga_records for header_id: {header_id}")
    try:
        # 1. Fetch all necessary data
        cur.execute("""
            SELECT h.id, h.encounter_id, h.created_at AS assessment_date, 
                   e.patient_id, p.hn, p.full_name, p.birth_date,
                   TIMESTAMPDIFF(YEAR, p.birth_date, CURDATE()) AS age_year
            FROM cga_headers h
            JOIN encounters e ON h.encounter_id = e.id
            JOIN patients p ON e.patient_id = p.id
            WHERE h.id = %s
        """, (header_id,))
        base_info = cur.fetchone()
        
        if not base_info:
            print(f"DEBUG: No base_info found for header_id {header_id}. Sync aborted.")
            return

        print(f"DEBUG: Syncing data for Patient: {base_info['full_name']} (HN: {base_info['hn']})")

        # Scores
        cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (header_id,))
        m_row = cur.fetchone()
        mmse_score = m_row['total_score'] if m_row else 0
        
        cur.execute("SELECT total_score FROM assessment_tgds WHERE cga_id=%s", (header_id,))
        t_row = cur.fetchone()
        tgds_score = t_row['total_score'] if t_row else 0

        # Answers
        cur.execute("SELECT session_id FROM cga_headers WHERE id=%s", (header_id,))
        sess_id = cur.fetchone()['session_id']
        
        cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s", (sess_id,))
        answers = cur.fetchall()
        
        # 8Q Score Calculation logic
        q8_score_val = 0
        q8_weights = {1:1, 2:2, 3:4, 4:6, 5:8, 6:9, 7:9, 8:4}
        q3_val = 'no'
        q3_sub_val = 'no'

        # Parse Answers
        data_map = {
            "education": "3", "caregiver_name": "", "caregiver_relation": "", "emergency_phone": "",
            "smoke": "no", "alcohol": "no", "incontinence": "normal", "sleep_problem": "normal",
            "suicide_risk": "none", "vision_left": "normal", "vision_right": "normal", 
            "hearing_left": "normal", "hearing_right": "normal", "gender": "male"
        }
        
        for r in answers:
            inst = r['instrument']
            txt = r['answer_text']
            
            if inst == 'basic' and ':' in txt:
                k, v = txt.split(':', 1)
                if k in data_map: data_map[k] = v
            elif inst == 'incontinence': data_map['incontinence'] = txt
            elif inst == 'sleepProblems': data_map['sleep_problem'] = txt
            elif inst == 'suicideRisk': data_map['suicide_risk'] = txt
            elif inst == 'depression8Q':
                try:
                    q_idx = int(r['question_no'])
                    if txt == 'yes':
                        q8_score_val += q8_weights.get(q_idx, 0)
                        if q_idx == 3: q3_val = 'yes'
                except: pass
            elif inst == 'depression8Q_sub':
                q3_sub_val = txt

        if q3_val == 'yes' and q3_sub_val == 'yes':
            q8_score_val += 10
            # Vision Test (Left/Right) is now handled in 'basic' loop above
            # Hearing Test (Left/Right) also handled in 'basic' loop (hearing_left, hearing_right, hearing_left_detail, hearing_right_detail)

        # Hearing Logic: If abnormal, use detail text. Else 'ปกติ'
        hl_val = data_map.get('hearing_left', 'normal')
        hl_det = data_map.get('hearing_left_detail', '')
        if hl_val == 'abnormal':
            final_hl = hl_det if hl_det else 'ผิดปกติ (ไม่ระบุ)'
        else:
            final_hl = 'ปกติ'

        hr_val = data_map.get('hearing_right', 'normal')
        hr_det = data_map.get('hearing_right_detail', '')
        if hr_val == 'abnormal':
            final_hr = hr_det if hr_det else 'ผิดปกติ (ไม่ระบุ)'
        else:
            final_hr = 'ปกติ'

        # Incontinence Logic
        inc_val = data_map.get('incontinence', 'normal')
        inc_det = data_map.get('incontinence_detail', '')
        if inc_val == 'abnormal':
            final_inc = inc_det if inc_det else 'มีปัญหาการกลั้นปัสสาวะ (ไม่ระบุ)'
        else:
            final_inc = 'ปกติ'

        # Sleep Problem Logic (ทำเผื่อไว้เลย คล้ายกัน)
        sl_val = data_map.get('sleep_problem', 'normal')
        sl_det = data_map.get('sleep_problem_detail', '')
        if sl_val == 'abnormal':
            final_sl = sl_det if sl_det else 'มีปัญหาการนอน (ไม่ระบุ)'
        else:
            final_sl = 'ปกติ'

        # Calc MMSE Result
        edu_code = data_map['education']
        cutoff = 22
        if edu_code == '1': cutoff = 14
        elif edu_code == '2': cutoff = 17
        mmse_res = 'เสี่ยง' if mmse_score <= cutoff else 'ปกติ'
        
        tgds_res = 'ซึมเศร้า' if tgds_score >= 7 else 'ปกติ'

        # แปลงรหัสการศึกษาเป็นข้อความภาษาไทย
        edu_map = {
            '1': 'ไม่ได้เรียน/อ่านเขียนไม่ได้',
            '2': 'ประถมศึกษา',
            '3': 'สูงกว่าประถมศึกษา'
        }
        edu_text = edu_map.get(edu_code, 'สูงกว่าประถมศึกษา') # Default

        # แปลงข้อมูลบุหรี่/สุรา เป็นภาษาไทย
        habit_map = {
            'no': 'ไม่เคย',
            'quit': 'เลิกแล้ว',
            'yes': 'ดื่ม/สูบ', # ใช้คำกลางๆ หรือจะแยกก็ได้
            'none': 'ไม่ระบุ'
        }
        # Smoke
        s_val = data_map.get('smoke', 'no')
        if s_val == 'no': s_th = 'ไม่สูบ'
        elif s_val == 'quit': s_th = 'เคยสูบแต่เลิกแล้ว'
        elif s_val == 'yes': s_th = 'สูบ'
        else: s_th = 'ไม่ระบุ'

        # Alcohol
        a_val = data_map.get('alcohol', 'none')
        a_amt = data_map.get('alcohol_daily_amount', '') # ดึงจำนวนแก้ว
        
        if a_val == 'none' or a_val == 'no': 
            a_th = 'ไม่ดื่ม'
            a_amt = '' # ถ้าไม่ดื่ม ไม่ควรมีจำนวน
        elif a_val == 'social': 
            a_th = 'ดื่มบางครั้ง'
            a_amt = '' # บางครั้งอาจไม่ระบุจำนวนต่อวัน
        elif a_val == 'daily' or a_val == 'yes': 
            a_th = 'ดื่มทุกวัน'
            # a_amt ใช้ค่าเดิมที่ดึงมา
        else: 
            a_th = 'ไม่ระบุ'

        # แปลง Suicide Risk เป็นภาษาไทย
        sr_val = data_map.get('suicide_risk', 'none')
        sr_th = 'มี' if sr_val == 'yes' else 'ไม่มี'

        # Prepare Payload
        record_data = {
            "encounter_id": base_info['encounter_id'],
            "patient_id": base_info['patient_id'],
            "hn": base_info['hn'],
            "full_name": base_info['full_name'],
            "birth_date": base_info['birth_date'],
            "assessed_date": str(base_info['assessment_date']),
            "age": base_info['age_year'],
            "gender": data_map.get('gender', 'male'),
            "education": edu_text, # เก็บเป็นข้อความแทนรหัส
            "caregiver_name": data_map['caregiver_name'],
            "caregiver_relation": data_map['caregiver_relation'],
            "emergency_phone": data_map['emergency_phone'],
            "smoke": s_th,
            "alcohol": a_th,
            "alcohol_amount": a_amt, # เพิ่มคอลัมน์จำนวนแก้ว
            "mmse_score": mmse_score,
            "mmse_result": mmse_res,
            "tgds_score": tgds_score,
            "tgds_result": tgds_res,
            "suicide_risk": sr_th, # เก็บเป็นภาษาไทย
            "incontinence": final_inc, # ใช้ค่าที่คำนวณ (ปกติ/รายละเอียด)
            "sleep_problem": final_sl, # ใช้ค่าที่คำนวณ (ปกติ/รายละเอียด)
            "vision_left": data_map['vision_left'], # ข้อความจาก Vision Test ตาซ้าย
            "vision_right": data_map['vision_right'], # ข้อความจาก Vision Test ตาขวา
            "hearing_left": final_hl, # ใช้ค่าที่คำนวณแล้ว (ปกติ / รายละเอียดผิดปกติ)
            "hearing_right": final_hr, # ใช้ค่าที่คำนวณแล้ว
            "q8_score": q8_score_val
        }

        # 2. Local Insert/Update (Check if exists first)
        try:
            cur.execute("SELECT id FROM cga_records WHERE encounter_id=%s", (base_info['encounter_id'],))
            existing = cur.fetchone()
            
            if existing:
                set_clause = ", ".join([f"{k}=%s" for k in record_data.keys()])
                vals = list(record_data.values()) + [base_info['encounter_id']]
                cur.execute(f"UPDATE cga_records SET {set_clause} WHERE encounter_id=%s", vals)
                print(f"DEBUG: Updated cga_records for encounter_id: {base_info['encounter_id']}")
            else:
                cols = ", ".join(record_data.keys())
                placeholders = ", ".join(["%s"] * len(record_data))
                vals = list(record_data.values())
                cur.execute(f"INSERT INTO cga_records ({cols}) VALUES ({placeholders})", vals)
                print(f"DEBUG: Inserted new cga_records for encounter_id: {base_info['encounter_id']}")
            conn.commit()
        except Exception as e:
            print(f"Local cga_records update failed: {e}")

        # 3. Cloud Sync (Resolve Cloud IDs first)
        try:
            supabase = get_supabase_client()
            # 🟢 ค้นหา Patient ID บน Cloud โดยใช้ HN (ซึ่งเป็น Unique และตรงกันทั้งสองที่)
            sb_p_res = supabase.table("patients").select("id").eq("hn", base_info['hn']).execute()
            
            if sb_p_res.data:
                cloud_patient_id = sb_p_res.data[0]['id']
                
                # เตรียมข้อมูลสำหรับ Cloud (ลบฟิลด์ที่ไม่ต้องการออก)
                cloud_payload = record_data.copy()
                cloud_payload['patient_id'] = cloud_patient_id # ใช้ ID ของ Cloud แทน
                
                # ส่งข้อมูลขึ้น Cloud
                # 🟢 ปรับปรุง: ใช้ on_conflict=['hn', 'assessed_date'] หากตารางรองรับ หรือใช้ encounter_id ที่แมพแล้ว
                ok, msg = safe_supabase_sync("cga_records", cloud_payload, method='upsert', conflict_col='encounter_id')
                if ok:
                    print(f"DEBUG: Cloud sync SUCCESS for cga_records (HN: {base_info['hn']})")
                else:
                    print(f"DEBUG: Cloud sync FAILED for cga_records: {msg}")
                    # ลองส่งแบบ insert หาก upsert ติดปัญหาเรื่อง id
                    if "conflict" in msg.lower():
                        safe_supabase_sync("cga_records", cloud_payload, method='insert')
        except Exception as e:
            print(f"DEBUG: Cloud Sync Exception: {e}")
            
    except Exception as e:
        print(f"Sync to cga_records failed: {e}")


@nurse_bp.post('/assess/send_to_doctor/<int:header_id>', endpoint='send_to_doctor')
def send_to_doctor(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute("SELECT h.*, e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (header_id,))
        h_data = cur.fetchone()
        p_id = h_data['patient_id']
        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_raw = cur.fetchone()
        
        cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (header_id,))
        m_score = (cur.fetchone() or {'total_score':0})['total_score']
        cur.execute("SELECT total_score FROM assessment_tgds WHERE cga_id=%s", (header_id,))
        t_score = (cur.fetchone() or {'total_score':0})['total_score']
        
        # 🟢 ดึงข้อมูล Suicide Risk เพื่อคำนวณความเสี่ยงใหม่
        cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='suicideRisk'", (h_data['session_id'],))
        sr_res = cur.fetchone()
        has_suicide_risk = (sr_res['answer_text'] == 'yes') if sr_res else False
        
        # คำนวณ Risk Level
        risk_lv = 'high' if (m_score <= 15 or t_score >= 10 or has_suicide_risk) else ('medium' if (m_score <= 23 or t_score >= 7) else 'low')

        final_hn = p_raw['hn']
        final_gcn = p_raw['gcn']
        
        if not final_hn or str(final_hn).startswith("TMP"):
            supabase = get_supabase_client()
            sb_res = supabase.table("patients").select("hn").execute()
            max_num = 0
            pattern = re.compile(r'^HN(\d+)$', re.IGNORECASE)
            for r in sb_res.data:
                if r.get('hn'):
                    m = pattern.match(str(r['hn']))
                    if m:
                        val = int(m.group(1))
                        if val < 1000000 and val > max_num:
                            max_num = val
            
            cur.execute("SELECT hn FROM patients WHERE hn LIKE 'HN%'")
            for r in cur.fetchall():
                m = pattern.match(str(r['hn']))
                if m:
                    val = int(m.group(1))
                    if val < 1000000 and val > max_num:
                        max_num = val
            
            final_hn = f"HN{(max_num + 1):03d}"
            
            if not final_gcn:
                cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
                final_gcn = f"{(cur.fetchone()['c'] + 1):03d}"
            
            cur.execute("UPDATE patients SET hn=%s, gcn=%s WHERE id=%s", (final_hn, final_gcn, p_id))
            
            # อัปเดต HN จริงกลับเข้าไปใน cga_records ด้วย (ถ้ามีข้อมูลอยู่แล้ว)
            cur.execute("UPDATE cga_records SET hn=%s WHERE encounter_id=%s", (final_hn, h_data['encounter_id']))
            conn.commit()

        supabase = get_supabase_client()
        sex_map = {'male': 'ชาย', 'female': 'หญิง'}

        # ดึงข้อมูลผู้ดูแลจาก Local Answers
        cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (h_data['session_id'],))
        ans_rows = cur.fetchall()
        caregiver_info = {}
        for row in ans_rows:
            txt = row['answer_text']
            if ':' in txt:
                k, v = txt.split(':', 1)
                if k in ['caregiver_name', 'caregiver_relation', 'emergency_phone']:
                    caregiver_info[k] = v

        sb_p = {
            "hn": final_hn, 
            "gcn": str(final_gcn).zfill(3), 
            "full_name": p_raw['full_name'], 
            "phone": p_raw['phone'], 
            "address": p_raw['address'], 
            "sex": sex_map.get(p_raw['gender'], p_raw['gender']), 
            "birth_date": str(p_raw['birth_date']) if p_raw['birth_date'] else None,
            **caregiver_info # รวมข้อมูลผู้ดูแล
        }
        
        sync_errors = []
        
        # 1. ใช้ Safe Sync สำหรับทะเบียนผู้ป่วย
        ok, msg = safe_supabase_sync("patients", sb_p, method='upsert', conflict_col='hn')
        if not ok: sync_errors.append(f"ผู้ป่วย: {msg}")
        
        # 2. ส่งข้อมูลการมาตรวจ (Encounters) - จำเป็นมากเพื่อให้ Headers มีที่เกาะ
        cur.execute("SELECT * FROM encounters WHERE id = %s", (h_data['encounter_id'],))
        enc_raw = cur.fetchone()
        if enc_raw:
            sb_p_res = supabase.table("patients").select("id").eq("hn", final_hn).execute()
            if sb_p_res.data:
                enc_payload = {
                    "id": enc_raw['id'],
                    "patient_id": sb_p_res.data[0]['id'],
                    "encounter_date": str(enc_raw['encounter_date']),
                    "created_by": enc_raw['created_by']
                }
                ok, msg = safe_supabase_sync("encounters", enc_payload, method='upsert', conflict_col='id')
                if not ok: sync_errors.append(f"การมาตรวจ: {msg}")

        # คำนวณความเสี่ยง MMSE ตามระดับการศึกษา
        # ดึงข้อมูลระดับการศึกษาจาก basic info
        cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic' AND question_no=3", (h_data['session_id'],)) 
        # สมมติว่า question_no=3 คือ education (ต้องเช็คจาก form อีกที แต่เบื้องต้นใช้การดึงจาก answer_text ที่เก็บ key:value ดีกว่า)
        
        cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (h_data['session_id'],))
        basic_ans = cur.fetchall()
        edu_level = '3' # Default สูงกว่าประถม
        for ba in basic_ans:
            if ba['answer_text'].startswith('education:'):
                edu_level = ba['answer_text'].split(':')[1]
                break
        
        mmse_cutoff = 22
        if edu_level == '1': # ไม่ได้เรียน/อ่านเขียนไม่ได้
            mmse_cutoff = 14
        elif edu_level == '2': # ประถมศึกษา
            mmse_cutoff = 17
            
        is_mmse_risk = m_score <= mmse_cutoff

        # เตรียมข้อมูลเพิ่มเติมสำหรับ Consultation
        extra_consult = {
            "age": p_raw.get('age_year'),
            "cognition_status": "เสี่ยงภาวะสมองเสื่อม" if is_mmse_risk else "ปกติ",
            "health_behavior": "",
            "incontinence": "",
            "sleep_problem": "",
            "depression_2q": ""
        }
        
        # ดึงข้อมูลจากคำตอบ (answers)
        cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s", (h_data['session_id'],))
        all_ans = cur.fetchall()
        
        hb_list = []
        dep_2q_list = []
        
        for r in all_ans:
            inst = r['instrument']
            txt = r['answer_text']
            
            if inst == 'basic' and ':' in txt:
                k, v = txt.split(':', 1)
                if k == 'age': extra_consult['age'] = int(v) if v.isdigit() else p_raw.get('age_year')
                elif k in ['smoke', 'alcohol']:
                     if v and v != 'no': hb_list.append(f"{k}:{v}")
            elif inst == 'incontinence':
                extra_consult['incontinence'] = txt
            elif inst == 'sleepProblems':
                extra_consult['sleep_problem'] = txt
            elif inst == 'depression2Q':
                dep_2q_list.append(f"Q{r['question_no']}:{txt}")

        if hb_list: extra_consult['health_behavior'] = ", ".join(hb_list)
        if dep_2q_list: extra_consult['depression_2q'] = ", ".join(dep_2q_list)

        consult_data = {
            "hn": final_hn, 
            "patient_name": p_raw['full_name'], 
            "nurse_name": str(session.get('full_name') or session.get('username')), 
            "mmse_score": int(m_score), 
            "tgds_score": int(t_score), 
            "priority": request.form.get('priority', 'normal'), 
            "note_from_nurse": request.form.get('nurse_note', ''), 
            "status": "pending",
            **extra_consult
        }
        # 3. ส่งใบส่งตัวหาหมอ
        ok, msg = safe_supabase_sync("consultations", consult_data, method='insert')
        if not ok: sync_errors.append(f"ใบส่งตัว: {msg}")
        
        # 4. อัปเดตสถานะและระดับความเสี่ยงใน Cloud CGA Header ด้วย
        cga_update = {
            "encounter_id": h_data['encounter_id'],
            "status": "sent_to_doctor",
            "overall_risk": risk_lv,
            "risk_level": risk_lv
        }
        ok, msg = safe_supabase_sync("cga_headers", cga_update, method='upsert', conflict_col='encounter_id')
        if not ok: sync_errors.append(f"สรุป CGA: {msg}")
        
        cur.execute("UPDATE cga_headers SET status='sent_to_doctor' WHERE id=%s", (header_id,))
        conn.commit()

        # 5. Sync to Flat Table (cga_records)
        _sync_to_cga_records(header_id, conn, cur)

        if sync_errors:
            flash(f"ส่งต่อข้อมูลสำเร็จ แต่มีปัญหาการ Sync บางส่วน: {'; '.join(sync_errors)}", "warning")
        else:
            flash(f"ส่งต่อข้อมูลคนไข้ {final_hn} ให้แพทย์เรียบร้อยแล้ว", "success")
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
    finally:
        cur.close()
        conn.close()

@nurse_bp.post('/assess/finalize/<int:header_id>', endpoint='assess_finalize')
def assess_finalize(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    
    try:
        # 1. ดึงข้อมูลที่จำเป็นมาเตรียมไว้
        cur.execute("SELECT h.*, e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (header_id,))
        h_data = cur.fetchone()
        if not h_data:
             flash("ไม่พบข้อมูลการประเมิน", "danger")
             return redirect(url_for('nurse.dashboard'))
             
        p_id = h_data['patient_id']
        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_row = cur.fetchone()
        
        # เตรียมข้อมูลสำหรับ Sync
        sex_map = {'male': 'ชาย', 'female': 'หญิง'}
        
        # ดึงข้อมูลผู้ดูแล
        cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (h_data['session_id'],))
        ans_rows = cur.fetchall()
        caregiver_info = {}
        for row in ans_rows:
            txt = row['answer_text']
            if ':' in txt:
                k, v = txt.split(':', 1)
                if k in ['caregiver_name', 'caregiver_relation', 'emergency_phone']:
                    caregiver_info[k] = v

        sb_p = {
            "hn": p_row['hn'], 
            "gcn": str(p_row['gcn']).zfill(3) if p_row['gcn'] else None,
            "full_name": p_row['full_name'], 
            "phone": p_row['phone'], 
            "address": p_row['address'], 
            "sex": sex_map.get(p_row['gender'], p_row['gender']), 
            "birth_date": str(p_row['birth_date']) if p_row['birth_date'] else None,
            **caregiver_info
        }

        sync_errors = []
        
        # 2. Sync Patients
        ok, msg = safe_supabase_sync("patients", sb_p, method='upsert', conflict_col='hn')
        if not ok: sync_errors.append(f"ผู้ป่วย: {msg}")

        # 3. Sync Encounters (เพื่อให้ Header มีที่เกาะ)
        cur.execute("SELECT * FROM encounters WHERE id = %s", (h_data['encounter_id'],))
        enc_raw = cur.fetchone()
        if enc_raw:
             supabase = get_supabase_client()
             # ต้องหา ID ของ patient ใน Supabase ก่อน (ถ้าใช้ ID เป็น FK) หรือส่งเป็น HN ถ้า Cloud รองรับ
             # ในที่นี้สมมติว่า Cloud ใช้ ID เป็น FK เหมือน Local
             try:
                sb_p_res = supabase.table("patients").select("id").eq("hn", p_row['hn']).execute()
                if sb_p_res.data:
                    enc_payload = {
                        "id": enc_raw['id'],
                        "patient_id": sb_p_res.data[0]['id'],
                        "encounter_date": str(enc_raw['encounter_date']),
                        "created_by": enc_raw['created_by']
                    }
                    ok, msg = safe_supabase_sync("encounters", enc_payload, method='upsert', conflict_col='id')
                    if not ok: sync_errors.append(f"การมาตรวจ: {msg}")
             except Exception as e:
                sync_errors.append(f"เชื่อมโยงผู้ป่วย: {str(e)}")

        # 4. Sync CGA Headers (Update Status)
        # ตรวจสอบ Risk Level ล่าสุดก่อนส่ง
        risk_lv = h_data.get('overall_risk', 'low') 
        cga_sb_data = {
            "encounter_id": h_data['encounter_id'], 
            "assessed_by": int(session.get('user_id', 0)), 
            "assessment_date": str(date.today()), 
            "risk_level": risk_lv, 
            "overall_risk": risk_lv, 
            "status": "completed",
            "is_completed": True
        }
        ok, msg = safe_supabase_sync("cga_headers", cga_sb_data, method='upsert', conflict_col='encounter_id')
        if not ok: sync_errors.append(f"สรุป CGA: {msg}")

        # 5. Local Update (Confirm Status)
        cur.execute("UPDATE cga_headers SET status='completed' WHERE id=%s", (header_id,))
        conn.commit()

        # 6. Sync to Flat Table
        _sync_to_cga_records(header_id, conn, cur)

        if sync_errors:
            flash(f"บันทึกเสร็จสิ้น แต่ Sync บางรายการไม่สำเร็จ: {'; '.join(sync_errors)}", "warning")
        else:
            flash("บันทึกการประเมินและ Sync ข้อมูลสำเร็จ", "success")
            
        return redirect(url_for('nurse.dashboard'))

    except Exception as e:
        conn.rollback()
        flash(f"เกิดข้อผิดพลาด: {e}", "danger")
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
    finally:
        cur.close()
        conn.close()

@nurse_bp.get("/patients", endpoint="patients")
def patients():
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    search = request.args.get("search", "").strip()
    
    # 🟢 ปรับปรุง: ดึงจาก Local MySQL เป็นหลักเพื่อให้เห็นข้อมูลล่าสุดที่แก้ไขในเครื่อง
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    rows = []
    try:
        query = "SELECT * FROM patients"
        params = []
        if search:
            query += " WHERE hn LIKE %s OR gcn LIKE %s OR full_name LIKE %s"
            search_param = f"%{search}%"
            params = [search_param, search_param, search_param]
        
        query += " ORDER BY id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        
        for p in rows:
            if p.get('hn'):
                clean_hn = str(p['hn']).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    p['hn'] = f"HN{clean_hn.zfill(3)}"
            if p.get('gcn'):
                p['gcn'] = str(p['gcn']).zfill(3)
    except Exception as e:
        flash(f"Database Error: {e}", "danger")
    finally:
        cur.close()
        conn.close()
        
    return render_template("nurse/patients.html", patients=rows, search_val=search)

@nurse_bp.get("/patient/history/<string:hn>", endpoint="patient_history")
def patient_history(hn: str):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute("SELECT * FROM patients WHERE hn = %s", (hn,))
        patient = cur.fetchone()
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วยในระบบ Local", "danger")
            return redirect(url_for("nurse.patients"))
        
        # 🟢 ดึงประวัติการประเมินจาก cga_records
        query = """
            SELECT 
                encounter_id as header_id, 
                created_at, 
                'completed' as status, 
                mmse_score, 
                tgds_score 
            FROM cga_records 
            WHERE hn = %s 
            ORDER BY created_at DESC
        """
        cur.execute(query, (hn,))
        history = cur.fetchall()
        return render_template("nurse/patient_history.html", patient=patient, history=history)
    finally:
        cur.close()
        conn.close()

@nurse_bp.get("/patient/edit/<string:hn>", endpoint="patient_edit")
def patient_edit(hn: str):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute("SELECT * FROM patients WHERE hn = %s", (hn,))
        patient = cur.fetchone()
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วย", "danger")
            return redirect(url_for("nurse.patients"))
        return render_template("nurse/patient_edit.html", patient=patient)
    finally:
        cur.close()
        conn.close()

@nurse_bp.post("/patient/update/<string:hn>", endpoint="patient_update")
def patient_update(hn: str):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    f = request.form
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        sex_val = 'male' if f.get('gender')=='male' else ('female' if f.get('gender')=='female' else None)
        cur.execute("UPDATE patients SET full_name=%s, phone=%s, address=%s, gender=%s, birth_date=%s WHERE hn=%s",
                    (f.get('full_name'), f.get('phone'), f.get('address'), sex_val, f.get('birthdate') or None, hn))
        
        # 🟢 อัปเดตชื่อใน cga_records ด้วยเพื่อให้ในหน้ารายงานเปลี่ยนตาม
        try:
            cur.execute("UPDATE cga_records SET full_name=%s WHERE hn=%s", (f.get('full_name'), hn))
        except: pass

        conn.commit()
        try:
            supabase = get_supabase_client()
            supabase_sex = 'ชาย' if f.get('gender') == 'male' else ('หญิง' if f.get('gender') == 'female' else None)
            sb_data = {
                "full_name": f.get('full_name'), 
                "phone": f.get('phone'), 
                "address": f.get('address'), 
                "sex": supabase_sex, 
                "birth_date": f.get('birthdate') or None
            }
            # ใช้ Safe Sync เพื่อป้องกัน Error จากคอลัมน์ที่ไม่มี
            safe_supabase_sync("patients", sb_data, method='upsert', conflict_col='hn')
        except:
            pass
        flash("บันทึกการแก้ไขข้อมูลเรียบร้อยแล้ว", "success")
        return redirect(url_for("nurse.patients"))
    except Exception as e:
        conn.rollback()
        flash(f"เกิดข้อผิดพลาด: {e}", "danger")
        return redirect(url_for("nurse.patient_edit", hn=hn))
    finally:
        cur.close()
        conn.close()

@nurse_bp.post("/patient/delete/<string:hn>", endpoint="patient_delete")
def patient_delete(hn: str):
    if not _require_nurse():
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        # 1. หา patient_id
        cur.execute("SELECT id FROM patients WHERE hn = %s", (hn,))
        patient = cur.fetchone()
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วย", "warning")
            return redirect(url_for("nurse.patients"))
        p_id = patient['id']

        # 2. ล้างข้อมูลในตารางที่เกี่ยวข้อง (Cascaded Cleanup)
        # หา encounters ทั้งหมดของคนไข้คนนี้
        cur.execute("SELECT id FROM encounters WHERE patient_id = %s", (p_id,))
        enc_ids = [r['id'] for r in cur.fetchall()]

        for e_id in enc_ids:
            # หา cga_headers
            cur.execute("SELECT id FROM cga_headers WHERE encounter_id = %s", (e_id,))
            h_ids = [r['id'] for r in cur.fetchall()]
            for h_id in h_ids:
                # ลบ MMSE/TGDS Items
                cur.execute("DELETE FROM assessment_mmse_items WHERE mmse_id IN (SELECT id FROM assessment_mmse WHERE cga_id = %s)", (h_id,))
                cur.execute("DELETE FROM assessment_mmse WHERE cga_id = %s", (h_id,))
                cur.execute("DELETE FROM assessment_tgds_items WHERE tgds_id IN (SELECT id FROM assessment_tgds WHERE cga_id = %s)", (h_id,))
                cur.execute("DELETE FROM assessment_tgds WHERE cga_id = %s", (h_id,))
                cur.execute("DELETE FROM cga_headers WHERE id = %s", (h_id,))

            # ลบ Answers & Sessions
            cur.execute("DELETE FROM assessment_answers WHERE session_id IN (SELECT id FROM assessment_sessions WHERE encounter_id = %s)", (e_id,))
            cur.execute("DELETE FROM assessment_sessions WHERE encounter_id = %s", (e_id,))
            
            # ลบ Summary Records
            cur.execute("DELETE FROM cga_records WHERE encounter_id = %s", (e_id,))
            
            # ลบ Encounter
            cur.execute("DELETE FROM encounters WHERE id = %s", (e_id,))

        # 3. ลบข้อมูลผู้ป่วย (Local)
        cur.execute("DELETE FROM patients WHERE id = %s", (p_id,))
        conn.commit()

        # 4. ลบข้อมูลใน Cloud (Supabase)
        try:
            supabase = get_supabase_client()
            # ลบ cga_records บน cloud ก่อน
            supabase.table("cga_records").delete().eq("hn", hn).execute()
            # ลบผู้ป่วยบน cloud
            supabase.table("patients").delete().eq("hn", hn).execute()
        except Exception as cloud_e:
            print(f"Cloud Delete Sync Error: {cloud_e}")

        flash("ลบข้อมูลผู้ป่วยและประวัติการประเมินทั้งหมดเรียบร้อยแล้ว", "success")
    except Exception as e:
        conn.rollback()
        flash(f"ไม่สามารถลบข้อมูลได้: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("nurse.patients"))

@nurse_bp.get("/api/patients", endpoint="api_patients")
def api_patients():
    if not _require_nurse():
        return {"error": "unauthorized"}, 401
    search = request.args.get("search", "").strip()
    conn = get_db_connection()
    if not conn:
        return {"error": "database connection failed"}, 500
    cur = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM patients"
        params = []
        if search:
            query += " WHERE hn LIKE %s OR gcn LIKE %s OR full_name LIKE %s"
            search_param = f"%{search}%"
            params = [search_param, search_param, search_param]
        
        query += " ORDER BY id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # Clean data for JSON serialization
        for p in rows:
            if p.get("birth_date"): p["birth_date"] = str(p["birth_date"])
            if p.get("created_at"): p["created_at"] = str(p["created_at"])
            
        return {"patients": rows}
    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        cur.close()
        conn.close()
