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

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

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
        cur.execute("""
            SELECT h.encounter_id, h.session_id, e.patient_id 
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            WHERE h.id = %s
        """, (header_id,))
        ids = cur.fetchone()
        if not ids:
            return {"hn": "N/A", "gcn": "N/A"}
        
        p_id = ids["patient_id"]
        sess_id = ids["session_id"]
        
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
            "patient_id": p_id,
            "session_id": sess_id
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
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
        kpis["today"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)")
        kpis["week"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE())")
        kpis["month"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor')")
        kpis["total"] = cur.fetchone()["c"]

        supabase = get_supabase_client()
        sb_res = supabase.table("patients").select("*").order("id", desc=True).limit(5).execute()
        sb_patients = sb_res.data

        for p in sb_patients:
            if p.get('hn'):
                clean_hn = str(p['hn']).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    p['hn'] = f"HN{clean_hn.zfill(3)}"
            if p.get('gcn'):
                p['gcn'] = str(p['gcn']).zfill(3)

            cur.execute("""
                SELECT h.id AS header_id, m.total_score AS mmse_score, t.total_score AS tgds_score, h.created_at, h.overall_risk
                FROM cga_headers h
                JOIN encounters e ON e.id = h.encounter_id
                JOIN patients lp ON lp.id = e.patient_id
                LEFT JOIN assessment_mmse m ON m.cga_id = h.id
                LEFT JOIN assessment_tgds t ON t.cga_id = h.id
                WHERE lp.hn = %s ORDER BY h.created_at DESC LIMIT 1
            """, (p['hn'],))
            score = cur.fetchone()
            if score:
                p.update(score)
            else:
                p['mmse_score'] = None
                p['tgds_score'] = None
                p['created_at'] = datetime.now()
            recent_patients.append(p)
    except Exception as e:
        print("Dashboard Error:", e)
    finally:
        cur.close()
        conn.close()
    return render_template("nurse/dashboard.html", kpis=kpis, recent_patients=recent_patients, user=session.get("username"), role="พยาบาล")

@nurse_bp.get("/api/kpis", endpoint="api_kpis")
def api_kpis():
    if not _require_nurse():
        return {"error": "unauthorized"}, 401
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
        today = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)")
        week = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE())")
        month = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor')")
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
        cur.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN m.total_score <= 23 THEN 1 ELSE 0 END) as mmse_risk, 
                   SUM(CASE WHEN t.total_score >= 7 THEN 1 ELSE 0 END) as tgds_risk
            FROM cga_headers h
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id
            WHERE h.status IN ('completed','sent_to_doctor') AND DATE(h.created_at) BETWEEN %s AND %s
        """, (start_date, end_date))
        report_data['ov'] = cur.fetchone()
        
        cur.execute("""
            SELECT h.id as header_id, p.hn, p.full_name, p.birth_date, m.total_score as mmse, t.total_score as tgds, 
                   (SELECT answer_text FROM assessment_answers WHERE session_id=h.session_id AND instrument='suicideRisk' LIMIT 1) as suicide 
            FROM cga_headers h 
            JOIN encounters e ON e.id = h.encounter_id 
            JOIN patients p ON p.id = e.patient_id 
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id 
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id 
            WHERE h.status IN ('completed','sent_to_doctor') 
              AND (m.total_score <= 15 OR t.total_score >= 10 OR EXISTS(SELECT 1 FROM assessment_answers WHERE session_id=h.session_id AND instrument='suicideRisk' AND answer_text='yes')) 
            ORDER BY h.created_at DESC LIMIT 15
        """)
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
    data = _get_assess_data(conn, header_id)
    answers = _get_answers(conn, header_id, 'mmse')
    conn.close()
    return render_template('nurse/mmse.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), assess=data, answers=answers)

@nurse_bp.post('/assess/mmse/save/<int:header_id>', endpoint='assess_mmse_save')
def assess_mmse_save(header_id: int):
    if not _require_nurse():
        return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    f = request.form
    try:
        cur.execute("INSERT INTO assessment_mmse (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_mmse WHERE cga_id = %s", (header_id,))
        mm_id = cur.fetchone()['id']
        cur.execute("DELETE FROM assessment_mmse_items WHERE mmse_id = %s", (mm_id,))
        for k, v in f.items():
            if k.startswith('q') and k != 'q':
                try:
                    cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, k[1:], int(v)))
                except:
                    continue
        
        # บันทึกคะแนนรวม
        ts = f.get('total_score', 0)
        cur.execute("UPDATE assessment_mmse SET total_score=%s WHERE id=%s", (ts, mm_id))
        
        sess_id = _get_assess_data(conn, header_id).get('session_id')
        if sess_id and f.get('edu'):
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='mmse_edu'", (sess_id,))
            cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'mmse_edu', 0, %s)", (sess_id, f.get('edu')))
        
        conn.commit()
        if f.get('next_url'):
            return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_tgds', header_id=header_id))
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
        cur.execute("INSERT INTO assessment_tgds (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_tgds WHERE cga_id = %s", (header_id,))
        tg_id = cur.fetchone()['id']
        cur.execute("DELETE FROM assessment_tgds_items WHERE tgds_id = %s", (tg_id,))
        
        sess_id = _get_assess_data(conn, header_id).get('session_id')
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
        # ถ้าตอบ Q3=Yes (ได้ 4 ไปแล้ว) และ Q3_Sub=Yes (ควบคุมไม่ได้) -> บวกเพิ่ม 10 เป็น 14
        if q3_val == 'yes' and q3_sub_val == 'yes':
            q8_score += 10

        if sess_id:
            sr_val = 'yes' if has_suicide_risk else 'none'
            cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'suicideRisk',1,%s)", (sess_id, sr_val))
            # Save 8Q Total Score (Optional: save to answers or scores table)
            # แต่เดี๋ยวเราจะ update ลง cga_records ตอนจบ
        
        cur.execute("UPDATE assessment_tgds SET total_score=%s WHERE id=%s", (score, tg_id))
        
        next_url = f.get('next_url')
        if next_url and 'summary' not in next_url:
            conn.commit()
            return redirect(next_url)

        # 🟢 2. คำนวณความเสี่ยงรวม (Risk Level)
        cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (header_id,))
        mmse_row = cur.fetchone(); m_score = mmse_row['total_score'] if mmse_row else 0
        risk_lv = 'high' if (m_score <= 15 or score >= 10 or has_suicide_risk) else ('medium' if (m_score <= 23 or score >= 7) else 'low')
        print(f"DEBUG: Calculated Risk Level: {risk_lv} (MMSE: {m_score}, TGDS: {score})")

        # 3. Finalize IDs and Update Local Header
        cur.execute("UPDATE cga_headers SET status='completed', overall_risk=%s WHERE id=%s", (risk_lv, header_id))
        
        cur.execute("SELECT h.*, e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (header_id,))
        h_data = cur.fetchone(); p_id = h_data['patient_id']
        
        # Update 8Q Score to cga_records
        try:
            cur.execute("UPDATE cga_records SET q8_score=%s WHERE encounter_id=%s", (q8_score, h_data['encounter_id']))
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
                    if val < 1000000 and val > max_num: max_num = val
            
            final_hn = f"HN{(max_num + 1):03d}"
            
        if not final_gcn:
            cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status IN ('completed','sent_to_doctor') AND DATE(created_at) = CURDATE()")
            final_gcn = f"{(cur.fetchone()['c'] + 1):03d}"
        
        cur.execute("UPDATE patients SET hn=%s, gcn=%s WHERE id=%s", (final_hn, final_gcn, p_id))
        conn.commit()

        # 🟢 CLOUD SYNC
        sync_errors = []
        try:
            cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
            p_latest = cur.fetchone(); sex_map = {'male': 'ชาย', 'female': 'หญิง'}

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
                "hn": p_latest['hn'], "gcn": str(p_latest['gcn']).zfill(3), 
                "full_name": p_latest['full_name'], "phone": p_latest['phone'], 
                "address": p_latest['address'], "sex": sex_map.get(p_latest['gender'], p_latest['gender']), 
                "birth_date": str(p_latest['birth_date']) if p_latest['birth_date'] else None,
                **caregiver_info # รวมข้อมูลผู้ดูแล
            }
            # 1. ส่งข้อมูลผู้ป่วย
            ok, msg = safe_supabase_sync("patients", sb_p, method='upsert', conflict_col='hn')
            if not ok: sync_errors.append(f"ผู้ป่วย: {msg}")
            
            # 2. ส่งข้อมูลการมาตรวจ (Encounters) - จำเป็นมากเพื่อให้ Headers มีที่เกาะ
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
                    ok, msg = safe_supabase_sync("encounters", enc_payload, method='upsert', conflict_col='id')
                    if not ok: sync_errors.append(f"การมาตรวจ: {msg}")

            # 3. ส่งสรุป CGA (จะผ่านได้เพราะมี Encounter แล้ว)
            cga_sb_data = {
                "encounter_id": h_data['encounter_id'], 
                "assessed_by": int(session.get('user_id', 0)), 
                "assessment_date": str(date.today()), 
                "risk_level": risk_lv, 
                "overall_risk": risk_lv, # ส่งทั้งสองแบบเพื่อความชัวร์
                "status": "completed",
                "is_completed": True
            }
            ok, msg = safe_supabase_sync("cga_headers", cga_sb_data, method='upsert', conflict_col='encounter_id')
            if not ok: sync_errors.append(f"สรุป CGA: {msg}")
            
            if sync_errors:
                flash("บันทึก Local สำเร็จ แต่ Sync ไป Cloud ไม่ครบ: " + "; ".join(sync_errors), "warning")
            else:
                flash("บันทึกและ Sync ข้อมูลไป Cloud สำเร็จ", "success")

        except Exception as e: 
            print("Sync Error:", e)
            flash(f"บันทึก Local สำเร็จ แต่เกิดข้อผิดพลาดในการ Sync: {e}", "warning")
            
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
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
    
    cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (header_id,))
    m_row = cur.fetchone()
    m_score = m_row['total_score'] if m_row and m_row['total_score'] is not None else 0
    
    cur.execute("SELECT total_score FROM assessment_tgds WHERE cga_id=%s", (header_id,))
    t_row = cur.fetchone()
    t_score = t_row['total_score'] if t_row else 0
    
    # ดึงคะแนน 8Q (q8_score) จาก cga_records
    q8_val = 0
    try:
        cur.execute("SELECT q8_score FROM cga_records WHERE encounter_id=%s", (data.get('encounter_id'),))
        q8_row = cur.fetchone()
        if q8_row: q8_val = q8_row['q8_score']
    except:
        pass
    
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
    
    dep_2q_txt = []
    hb_txt = []
    
    for r in all_ans:
        inst = r['instrument']
        val = r['answer_text']
        if inst == 'depression2Q':
            # แปลง yes/no เป็น มี/ไม่มี
            disp_val = 'มี' if val == 'yes' else 'ไม่มี'
            dep_2q_txt.append(f"Q{r['question_no']}: {disp_val}")
        elif inst == 'basic' and ':' in val:
            k, v = val.split(':', 1)
            if k in ['smoke', 'alcohol'] and v != 'no':
                label = "สูบบุหรี่" if k == 'smoke' else "ดื่มสุรา"
                hb_txt.append(f"{label} ({v})")

    dep_2q_display = ", ".join(dep_2q_txt) if dep_2q_txt else "-"
    hb_display = ", ".join(hb_txt) if hb_txt else "ไม่มีพฤติกรรมเสี่ยง"
    
    # ดึงรายละเอียดคำตอบรายข้อ (สำหรับ Modal ดูรายละเอียด)
    mmse_details = {}
    tgds_details = {}
    
    # MMSE Items
    cur.execute("""
        SELECT question_no, score 
        FROM assessment_mmse_items 
        WHERE mmse_id = (SELECT id FROM assessment_mmse WHERE cga_id=%s ORDER BY id DESC LIMIT 1)
    """, (header_id,))
    for r in cur.fetchall():
        mmse_details[r['question_no']] = r['score']
        
    # TGDS Items
    cur.execute("""
        SELECT question_no, answer 
        FROM assessment_tgds_items 
        WHERE tgds_id = (SELECT id FROM assessment_tgds WHERE cga_id=%s ORDER BY id DESC LIMIT 1)
    """, (header_id,))
    for r in cur.fetchall():
        tgds_details[r['question_no']] = 'ใช่' if r['answer']==1 else 'ไม่ใช่'

    cur.execute("SELECT status FROM cga_headers WHERE id=%s", (header_id,))
    h_status = cur.fetchone()['status']
    
    # ดึงระดับการศึกษา
    cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (data.get('session_id'),))
    b_ans = cur.fetchall()
    edu = '3'
    for r in b_ans:
        if r['answer_text'].startswith('education:'):
            edu = r['answer_text'].split(':')[1]
            break

    mmse_total = 30
    mmse_threshold = 22 # default (สูงกว่าประถม cutoff ที่ 22 -> <=22 เสี่ยง)
    
    if edu == '1': # ไม่ได้เรียน/อ่านเขียนไม่ได้
        mmse_total = 23 # คะแนนเต็มเปลี่ยนด้วยไหม? ตามโจทย์บอกแค่ cutoff แต่ปกติแบบทดสอบสำหรับคนอ่านเขียนไม่ได้คะแนนเต็มจะลดลง
        mmse_threshold = 14
    elif edu == '2': # ประถม
        mmse_total = 30
        mmse_threshold = 17
    
    # Logic: Score <= Threshold คือ "เสี่ยง" (Suspected)
    mmse_risk_status = 'suspected' if m_score <= mmse_threshold else 'normal'
    
    cur.execute("SELECT e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (header_id,))
    p_id = cur.fetchone()['patient_id']
    cur.execute("SELECT hn, gcn FROM patients WHERE id = %s", (p_id,))
    fresh_p = cur.fetchone()
    
    cur.close()
    conn.close()
    return render_template('nurse/summary.html', header_id=header_id, hn=fresh_p['hn'], gcn=fresh_p['gcn'], patient=data, date=date.today().strftime('%d/%m/%Y'), user={'name': session.get('full_name')}, mmse_score=m_score, mmse_total=mmse_total, mmse_risk=mmse_risk_status, mmse_threshold=mmse_threshold, tgds_score=t_score, tgds_risk=('normal' if t_score < 7 else 'suspected'), tgds_risk_label=('ปกติ' if t_score < 7 else 'มีภาวะซึมเศร้า'), suicide_risk=sr_val, incontinence=inc_val, sleep=sl_val, status=h_status, dep_2q=dep_2q_display, health_behavior=hb_display, mmse_details=mmse_details, tgds_details=tgds_details, q8_score=q8_val)

# Helper function to sync data to cga_records (Flat Table)
def _sync_to_cga_records(header_id, conn, cur):
    """
    Rathers all data for a specific CGA header and inserts/updates it into cga_records table.
    Handles both Local and Cloud sync.
    """
    try:
        # 1. Fetch all necessary data
        cur.execute("""
            SELECT h.id, h.encounter_id, h.assessed_at AS assessment_date, 
                   e.patient_id, p.hn, p.full_name, p.birth_date,
                   TIMESTAMPDIFF(YEAR, p.birth_date, CURDATE()) AS age_year
            FROM cga_headers h
            JOIN encounters e ON h.encounter_id = e.id
            JOIN patients p ON e.patient_id = p.id
            WHERE h.id = %s
        """, (header_id,))
        base_info = cur.fetchone()
        if not base_info: return

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
        
        # Parse Answers
        data_map = {
            "education": "3", "caregiver_name": "", "caregiver_relation": "", "emergency_phone": "",
            "smoke": "no", "alcohol": "no", "incontinence": "normal", "sleep_problem": "normal",
            "suicide_risk": "none", "vision_left": "normal", "vision_right": "normal", 
            "hearing_left": "normal", "hearing_right": "normal"
        }
        
        for r in answers:
            inst = r['instrument']
            txt = r['answer_text']
            
            if inst == 'basic' and ':' in txt:
                k, v = txt.split(':', 1)
                if k in data_map: data_map[k] = v
                elif k == 'education': data_map['education'] = v
            elif inst == 'incontinence': data_map['incontinence'] = txt
            elif inst == 'sleepProblems': data_map['sleep_problem'] = txt
            elif inst == 'suicideRisk': data_map['suicide_risk'] = txt
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
            "assessed_date": str(base_info['assessment_date']),
            "age": base_info['age_year'],
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
            "hearing_right": final_hr # ใช้ค่าที่คำนวณแล้ว
        }

        # 2. Local Insert/Update (Check if exists first)
        # Note: Local DB might need `cga_records` table created first. Assuming it exists.
        try:
            # Simple check
            cur.execute("SELECT id FROM cga_records WHERE encounter_id=%s", (base_info['encounter_id'],))
            existing = cur.fetchone()
            
            if existing:
                # Update
                set_clause = ", ".join([f"{k}=%s" for k in record_data.keys()])
                vals = list(record_data.values()) + [base_info['encounter_id']]
                cur.execute(f"UPDATE cga_records SET {set_clause} WHERE encounter_id=%s", vals)
            else:
                # Insert
                cols = ", ".join(record_data.keys())
                placeholders = ", ".join(["%s"] * len(record_data))
                vals = list(record_data.values())
                cur.execute(f"INSERT INTO cga_records ({cols}) VALUES ({placeholders})", vals)
            conn.commit()
        except Exception as e:
            print(f"Local cga_records update failed: {e}")

        # 3. Cloud Sync (Resolve Cloud IDs first)
        try:
            supabase = get_supabase_client()
            # หา ID ของผู้ป่วยใน Cloud จาก HN
            sb_p = supabase.table("patients").select("id").eq("hn", base_info['hn']).execute()
            
            # หา ID ของ Encounter ใน Cloud (ถ้ายังไม่มีอาจต้องข้าม หรือใช้ Logic อื่น แต่ปกติ Encounter ควร Sync ไปก่อนแล้ว)
            # แต่เพื่อความง่าย เราจะใช้ encounter_id ของ Local ไปก่อนสำหรับ encounter_id (เพราะมันไม่มี Natural Key อื่นนอกจาก ID)
            # หรือถ้า Encounter ถูก Sync ด้วย ID เดียวกัน (Upsert by ID) ก็ใช้ได้เลย
            
            if sb_p.data:
                cloud_patient_id = sb_p.data[0]['id']
                
                # Clone data for Cloud Payload
                cloud_payload = record_data.copy()
                cloud_payload['patient_id'] = cloud_patient_id # ใช้ ID ของ Cloud
                
                # ส่งข้อมูล
                safe_supabase_sync("cga_records", cloud_payload, method='upsert', conflict_col='encounter_id')
        except Exception as e:
            print(f"Resolving Cloud IDs failed: {e}")
            
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
    try:
        supabase = get_supabase_client()
        query = supabase.table("patients").select("*")
        if search:
            query = query.or_(f"hn.ilike.%{search}%,gcn.ilike.%{search}%,full_name.ilike.%{search}%")
        response = query.order("id", desc=True).execute()
        rows = response.data
        for p in rows:
            if p.get('hn'):
                clean_hn = str(p['hn']).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    p['hn'] = f"HN{clean_hn.zfill(3)}"
            if p.get('gcn'):
                p['gcn'] = str(p['gcn']).zfill(3)
    except Exception as e:
        flash(f"Supabase Error: {e}", "danger")
        rows = []
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
        
        query = """
            SELECT h.id AS header_id, h.created_at, h.status, m.total_score AS mmse_score, t.total_score AS tgds_score 
            FROM cga_headers h 
            JOIN encounters e ON e.id = h.encounter_id 
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id 
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id 
            WHERE e.patient_id = %s 
            ORDER BY h.created_at DESC
        """
        cur.execute(query, (patient['id'],))
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
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM patients WHERE hn = %s", (hn,))
        conn.commit()
        try:
            supabase = get_supabase_client()
            supabase.table("patients").delete().eq("hn", hn).execute()
        except:
            pass
        flash("ลบข้อมูลผู้ป่วยเรียบร้อยแล้ว", "success")
    except Exception as e:
        conn.rollback()
        flash(f"ไม่สามารถลบข้อมูลได้: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("nurse.patients"))