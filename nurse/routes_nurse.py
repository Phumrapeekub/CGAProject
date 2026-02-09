from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Optional, Tuple, List
import mysql.connector
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from mysql.connector import Error  # type: ignore
from db.db import get_db_connection, get_supabase_client
from werkzeug.exceptions import Forbidden

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
def _get_val(row: dict, key: str, default=None):
    if not row: return default
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
        if not ids: return {"hn": "N/A", "gcn": "N/A"}
        
        p_id = _get_val(ids, "patient_id")
        sess_id = _get_val(ids, "session_id")
        
        # 1. หา HN จาก Local เพื่อไปค้นใน Supabase
        cur.execute("SELECT hn FROM patients WHERE id = %s", (p_id,))
        local_p = cur.fetchone()
        hn_to_find = local_p['hn'] if local_p else None

        # 2. ดึงข้อมูลจาก Supabase เป็นหลัก
        p_row = None
        if hn_to_find:
            try:
                supabase = get_supabase_client()
                sb_res = supabase.table("patients").select("*").eq("hn", hn_to_find).maybe_single().execute()
                p_row = sb_res.data
            except: pass

        # 3. ถ้า Supabase ไม่มี ให้ใช้ Local (Fallback)
        if not p_row:
            cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
            p_row = cur.fetchone()
        
        if not p_row: return {"hn": "HN -", "gcn": "---"}
        
        # ตรวจสอบคอลัมน์ที่มี
        bd_col = "birth_date" if "birth_date" in p_row else ("birthdate" if "birthdate" in p_row else None)
        sex_col = "sex" if "sex" in p_row else ("gender" if "gender" in p_row else None)
        addr_col = "address_text" if "address_text" in p_row else ("address" if "address" in p_row else None)
        age_col = "age_year" if "age_year" in p_row else ("age" if "age" in p_row else None)

        # Format HN/GCN สำหรับแสดงผล (Preview Next ID if Temp)
        hn_val = _get_val(p_row, "hn")
        gcn_val = _get_val(p_row, "gcn")
        
        # ถ้าเป็น HN ชั่วคราว ให้คำนวณเลขถัดไปมาโชว์ (Preview)
        if hn_val and str(hn_val).startswith("TMP"):
            try:
                # 🟢 ดึงข้อมูลจาก Supabase เพื่อหา MAX HN จริง
                supabase = get_supabase_client()
                sb_res = supabase.table("patients").select("hn").execute()
                
                # คำนวณหาเลขสูงสุดจาก HN001, HN002...
                max_val = 0
                for r in sb_res.data:
                    if r.get('hn'):
                        try:
                            num = int(str(r['hn']).upper().replace("HN", "").strip())
                            if num > max_val: max_val = num
                        except: continue
                
                hn_display = f"HN{(max_val + 1):03d}"
                
                # คำนวณ GCN ถัดไป (รีเซ็ตทุก 24 ชม. ตาม CURDATE)
                cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed' AND DATE(created_at) = CURDATE()")
                next_gcn = cur.fetchone()['c'] + 1
                gcn_display = f"{next_gcn:03d}"
            except Exception as e:
                print("Preview ID Error:", e)
                hn_display = "HN ---"
                gcn_display = "---"
        else:
            # ถ้ามีเลขจริงแล้ว ก็โชว์ตามปกติ
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
            "full_name": _get_val(p_row, "full_name"),
            "birth_date": _get_val(p_row, bd_col) if bd_col else None,
            "gender": _get_val(p_row, sex_col) if sex_col else None,
            "address_text": _get_val(p_row, addr_col) if addr_col else None,
            "phone": _get_val(p_row, "phone"),
            "age_year": _get_val(p_row, age_col) if age_col else None,
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
        
        # คืนค่า default ให้ฟิลด์ที่อยู่ที่อาจจะยังไม่มีข้อมูล เพื่อไม่ให้ template error
        addr_fields = ['house_no', 'moo', 'subdistrict', 'district', 'province', 'postal_code', 'caregiver_relation']
        for af in addr_fields:
            if af not in res: res[af] = ""
            
        return res
    except Exception as e: 
        print("Error in _get_assess_data:", e)
        return {"hn": "N/A", "gcn": "N/A"}
    finally: cur.close()

def _get_answers(conn, header_id, instrument):
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute(f"SELECT id FROM assessment_{instrument} WHERE cga_id = %s", (header_id,))
        h = cur.fetchone()
        if not h: return {}
        table = f"assessment_{instrument}_items"
        cur.execute(f"SHOW COLUMNS FROM {table}")
        cols = {r['Field'].lower() for r in cur.fetchall()}
        val_col = "answer" if "answer" in cols else ("answer_text" if "answer_text" in cols else "score")
        cur.execute(f"SELECT question_no, score, {val_col} as val FROM {table} WHERE {instrument}_id = %s", (h['id'],))
        return {r['question_no']: r for r in cur.fetchall()}
    except: return {}
    finally: cur.close()

# -------------------------
# Routes
# -------------------------
@nurse_bp.route("/dashboard", endpoint="dashboard")
def dashboard():
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    kpis = {"today": 0, "week": 0, "month": 0, "total": 0}
    recent_patients = []
    try:
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed' AND DATE(created_at) = CURDATE()")
        kpis["today"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed' AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)")
        kpis["week"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed' AND MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE())")
        kpis["month"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed'")
        kpis["total"] = cur.fetchone()["c"]

        # ดึงรายชื่อ 5 คนล่าสุดจาก Supabase
        supabase = get_supabase_client()
        sb_res = supabase.table("patients").select("*").order("id", desc=True).limit(5).execute()
        sb_patients = sb_res.data

        # นำรายชื่อมาหาคะแนนล่าสุดใน MySQL
        for p in sb_patients:
            # Format HN/GCN (HN001 style)
            if p.get('hn'):
                clean_hn = str(p['hn']).upper().replace("HN", "").strip()
                if clean_hn.isdigit():
                    p['hn'] = f"HN{clean_hn.zfill(3)}"
            if p.get('gcn'):
                p['gcn'] = str(p['gcn']).zfill(3)

            cur.execute("""
                SELECT 
                    h.id AS header_id, m.total_score AS mmse_score, 
                    t.total_score AS tgds_score, h.created_at
                FROM cga_headers h
                JOIN encounters e ON e.id = h.encounter_id
                JOIN patients lp ON lp.id = e.patient_id
                LEFT JOIN assessment_mmse m ON m.cga_id = h.id
                LEFT JOIN assessment_tgds t ON t.cga_id = h.id
                WHERE lp.hn = %s
                ORDER BY h.created_at DESC LIMIT 1
            """, (p['hn'],))
            score = cur.fetchone()
            if score:
                p.update(score)
            else:
                p['mmse_score'] = None
                p['tgds_score'] = None
                # ใช้เวลาปัจจุบันเป็นค่าสมมติถ้ายังไม่มีการประเมิน (เพื่อไม่ให้ .strftime พัง)
                p['created_at'] = datetime.now()
            recent_patients.append(p)

    except Exception as e:
        print("Dashboard Error:", e)
    finally:
        cur.close(); conn.close()
    return render_template("nurse/dashboard.html", kpis=kpis, recent_patients=recent_patients, user=session.get("username"), role="พยาบาล")

@nurse_bp.get("/reports", endpoint="reports")
def reports():
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    
    start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    
    report_data = {'start_date': start_date, 'end_date': end_date}
    try:
        # 1. Overview stats with Date Filter
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN m.total_score <= 23 THEN 1 ELSE 0 END) as mmse_risk,
                SUM(CASE WHEN t.total_score >= 5 THEN 1 ELSE 0 END) as tgds_risk
            FROM cga_headers h
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id
            WHERE h.status = 'completed' AND DATE(h.created_at) BETWEEN %s AND %s
        """, (start_date, end_date))
        ov = cur.fetchone()
        report_data['ov'] = ov

        # 2. BMI Analysis (Hospital Grade)
        cur.execute("""
            SELECT session_id, answer_text 
            FROM assessment_answers 
            WHERE instrument='basic' AND (answer_text LIKE 'height:%' OR answer_text LIKE 'weight:%')
        """)
        bmi_raw = {}
        for r in cur.fetchall():
            sid = r['session_id']
            if sid not in bmi_raw: bmi_raw[sid] = {}
            k, v = r['answer_text'].split(':')
            bmi_raw[sid][k] = float(v) if v else 0

        bmi_stats = {'underweight': 0, 'normal': 0, 'overweight': 0, 'obese': 0}
        for sid, v in bmi_raw.items():
            if v.get('height') and v.get('weight'):
                h_m = v['height'] / 100
                bmi = v['weight'] / (h_m * h_m)
                if bmi < 18.5: bmi_stats['underweight'] += 1
                elif bmi < 23: bmi_stats['normal'] += 1
                elif bmi < 25: bmi_stats['overweight'] += 1
                else: bmi_stats['obese'] += 1
        report_data['bmi'] = bmi_stats

        # 3. Chronic Disease Distribution
        cur.execute("""
            SELECT answer_text, COUNT(*) as count 
            FROM assessment_answers a
            JOIN assessment_sessions s ON s.id = a.session_id
            JOIN encounters e ON e.id = s.encounter_id
            WHERE a.instrument='basic' AND a.answer_text LIKE 'chronicDiseases:%'
              AND DATE(e.encounter_date) BETWEEN %s AND %s
            GROUP BY a.answer_text
        """, (start_date, end_date))
        diseases = {}
        for r in cur.fetchall():
            d_list = r['answer_text'].split(':')[1].split(',')
            for d in d_list:
                diseases[d] = diseases.get(d, 0) + r['count']
        report_data['diseases'] = diseases

        # 4. High Risk patients (Including header_id)
        cur.execute("""
            SELECT h.id as header_id, p.hn, p.full_name, p.age_year, m.total_score as mmse, t.total_score as tgds,
                   (SELECT answer_text FROM assessment_answers WHERE session_id=h.session_id AND instrument='suicideRisk' LIMIT 1) as suicide
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            JOIN patients p ON p.id = e.patient_id
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id
            WHERE h.status = 'completed' 
              AND (m.total_score <= 15 OR t.total_score >= 10 OR 
                   EXISTS(SELECT 1 FROM assessment_answers WHERE session_id=h.session_id AND instrument='suicideRisk' AND answer_text='yes'))
            ORDER BY h.created_at DESC LIMIT 15
        """)
        report_data['high_risk'] = cur.fetchall()

    except Exception as e: print("Report Error:", e)
    finally: cur.close(); conn.close()
    return render_template("nurse/summary_report.html", data=report_data, date=date.today().strftime('%d/%m/%Y'))

@nurse_bp.route("/assess/new", methods=["GET", "POST"], endpoint="assess_new")
def assess_new():
    if not _require_nurse(): return redirect(url_for("auth.login"))
    if request.method == "POST": return assess_create()
    return render_template("nurse/assess_new.html")

@nurse_bp.post("/assess/create", endpoint="assess_create")
def assess_create():
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # สร้าง HN ชั่วคราว (TEMP) เพื่อกัน Error NOT NULL
        import time
        temp_hn = f"TMP-{int(time.time())}"
        
        # Insert ด้วย HN ชั่วคราว (ยังไม่นับเป็น HN จริง)
        cur.execute("INSERT INTO patients (hn, gcn, full_name) VALUES (%s, NULL, 'รอกรอกข้อมูล')", (temp_hn,)); p_id = cur.lastrowid
        cur.execute("INSERT INTO encounters (patient_id, encounter_date, created_by) VALUES (%s, CURDATE(), %s)", (p_id, session.get("user_id"))); enc_id = cur.lastrowid
        cur.execute("INSERT INTO assessment_sessions (encounter_id, session_type, created_by) VALUES (%s, 'baseline', %s)", (enc_id, session.get("user_id"))); sess_id = cur.lastrowid
        
        cur.execute("INSERT INTO cga_headers (encounter_id, session_id, created_at, status) VALUES (%s, %s, NOW(), 'in_progress')", (enc_id, sess_id))
        
        conn.commit(); return redirect(url_for("nurse.assess_session", header_id=cur.lastrowid))
    except Exception as e:
        conn.rollback(); flash(f"Error: {e}", "danger"); return redirect(url_for("nurse.assess_new"))
    finally: cur.close(); conn.close()

@nurse_bp.get("/assess/session/<int:header_id>", endpoint="assess_session")
def assess_session(header_id: int):
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); assess = _get_assess_data(conn, header_id); conn.close()
    return render_template("nurse/assess_session.html", assess=assess, hn=assess.get("hn"), gcn=assess.get("gcn"), header_id=header_id)

@nurse_bp.post('/assess/step1/save/<int:header_id>', endpoint='assess_step1_save')
def assess_step1_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    f = request.form
    full_name = f"{f.get('name','')} {f.get('surname','')}".strip()
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    try:
        data = _get_assess_data(conn, header_id); p_id, sess_id = data.get("patient_id"), data.get("session_id")
        cur.execute("SHOW COLUMNS FROM patients"); p_cols = {r["Field"].lower() for r in cur.fetchall()}
        upd_cols = ["full_name = %s"]; upd_vals = [full_name]
        bd_col = "birth_date" if "birth_date" in p_cols else ("birthdate" if "birthdate" in p_cols else None)
        if bd_col: upd_cols.append(f"{bd_col} = %s"); upd_vals.append(f.get('birthdate') or None)
        sex_col = "sex" if "sex" in p_cols else ("gender" if "gender" in p_cols else None)
        if sex_col:
            db_gender = ('ชาย' if sex_col=='sex' else 'male') if f.get('gender')=='male' else (('หญิง' if sex_col=='sex' else 'female') if f.get('gender')=='female' else None)
            upd_cols.append(f"{sex_col} = %s"); upd_vals.append(db_gender)
        addr_col = "address_text" if "address_text" in p_cols else ("address" if "address" in p_cols else None)
        if addr_col: upd_cols.append(f"{addr_col} = %s"); upd_vals.append(f.get('address'))
        upd_cols.append("phone = %s"); upd_vals.append(f.get('phone'))
        age_col = "age_year" if "age_year" in p_cols else ("age" if "age" in p_cols else None)
        if age_col: upd_cols.append(f"{age_col} = %s"); upd_vals.append(f.get('age'))
        upd_vals.append(p_id)
        cur.execute(f"UPDATE patients SET {', '.join(upd_cols)} WHERE id=%s", tuple(upd_vals))
        if sess_id:
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='basic'", (sess_id,))
            fields = ['marry', 'live', 'smoke', 'alcohol', 'hearing_left', 'hearing_right', 'visionTest', 'height', 'weight', 'waist', 'otherDisease', 'age',
                      'house_no', 'moo', 'subdistrict', 'district', 'province', 'postal_code', 'hearing_left_detail', 'hearing_right_detail', 'emergency_phone', 'caregiver_name', 'caregiver_relation', 'alcohol_daily_amount']
            for k in fields:
                if f.get(k): cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'basic', 0, %s)", (sess_id, f"{k}:{f.get(k)}"))
            d = f.getlist('chronicDiseases')
            if d: cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'basic', 0, %s)", (sess_id, f"chronicDiseases:{','.join(d)}"))
        conn.commit()
        if f.get('next_url'): return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    except Exception as e:
        conn.rollback(); flash(f"Error: {e}", "danger"); return redirect(url_for('nurse.assess_session', header_id=header_id))
    finally: cur.close(); conn.close()

@nurse_bp.get('/assess/mmse/<int:header_id>', endpoint='assess_mmse')
def assess_mmse(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection(); data = _get_assess_data(conn, header_id); answers = _get_answers(conn, header_id, 'mmse'); conn.close()
    return render_template('nurse/mmse.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), assess=data, answers=answers)

@nurse_bp.post('/assess/mmse/save/<int:header_id>', endpoint='assess_mmse_save')
def assess_mmse_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True); f = request.form
    try:
        cur.execute("INSERT INTO assessment_mmse (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_mmse WHERE cga_id = %s", (header_id,))
        mm_id = cur.fetchone()['id']
        cur.execute("DELETE FROM assessment_mmse_items WHERE mmse_id = %s", (mm_id,))
        for k, v in f.items():
            if k.startswith('q') and k != 'q':
                try: cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mm_id, k[1:], int(v)))
                except: continue
        sess_id = _get_assess_data(conn, header_id).get('session_id')
        if sess_id and f.get('edu'):
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument='mmse_edu'", (sess_id,))
            cur.execute("INSERT INTO assessment_answers (session_id, instrument, question_no, answer_text) VALUES (%s, 'mmse_edu', 0, %s)", (sess_id, f.get('edu')))
        conn.commit()
        if f.get('next_url'): return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_tgds', header_id=header_id))
    except Exception as e:
        conn.rollback(); flash(f"Error: {e}", "danger"); return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    finally: cur.close(); conn.close()

@nurse_bp.get('/assess/tgds/<int:header_id>', endpoint='assess_tgds')
def assess_tgds(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    data = _get_assess_data(conn, header_id); tg_raw = _get_answers(conn, header_id, 'tgds'); other = {}
    try:
        sess_id = data.get('session_id')
        if sess_id:
            cur.execute("SELECT instrument, question_no, answer_text FROM assessment_answers WHERE session_id=%s", (sess_id,))
            for r in cur.fetchall():
                if r['instrument'] in ['incontinence','sleepProblems','suicideRisk']: other[r['instrument']] = r['answer_text']
                else: other[f"{r['instrument']}_{r['question_no']}"] = r['answer_text']
    except: pass
    comb = other.copy()
    for q, i in tg_raw.items(): comb[f"tgds15Answers_{q}"] = 'yes' if i['val'] == 1 else 'no'
    cur.close(); conn.close()
    return render_template('nurse/tgds15.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), assess=data, answers=comb)

@nurse_bp.post('/assess/tgds/save/<int:header_id>', endpoint='assess_tgds_save')
def assess_tgds_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True); f = request.form
    try:
        cur.execute("INSERT INTO assessment_tgds (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_tgds WHERE cga_id = %s", (header_id,))
        tg_id = cur.fetchone()['id']
        sess_id = _get_assess_data(conn, header_id).get('session_id')
        if sess_id:
            cur.execute("DELETE FROM assessment_answers WHERE session_id=%s AND instrument IN ('tgds15Answers','depression2Q','depression8Q','incontinence','sleepProblems','suicideRisk')", (sess_id,))
        score = 0; rev = [1, 5, 7, 11, 13]
        for k, v in f.items():
            if k.startswith('tgds15Answers_'):
                q = int(k.split('_')[1]); score += 1 if (q in rev and v=='no') or (q not in rev and v=='yes') else 0
                if sess_id: cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'tgds15Answers',%s,%s)", (sess_id, q, v))
            elif k.startswith('depression2Q_') and sess_id: cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'depression2Q',%s,%s)", (sess_id, (1 if 'q1' in k else 2), v))
            elif k.startswith('depression8Q_') and sess_id: cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,'depression8Q',%s,%s)", (sess_id, int(k.split('_')[1]), v))
            elif k in ['incontinence','sleepProblems','suicideRisk'] and sess_id: cur.execute("INSERT INTO assessment_answers (session_id,instrument,question_no,answer_text) VALUES (%s,%s,1,%s)", (sess_id, k, v))
        cur.execute("UPDATE assessment_tgds SET total_score=%s WHERE id=%s", (score, tg_id))
        cur.execute("UPDATE cga_headers SET status='completed' WHERE id=%s", (header_id,))
        
        # 🟢 รันเลข HN และ GCN จริงเมื่อทำประเมินเสร็จสิ้น (Step 3) เท่านั้น
        cur.execute("SELECT e.patient_id FROM cga_headers h JOIN encounters e ON e.id = h.encounter_id WHERE h.id = %s", (header_id,))
        p_id = cur.fetchone()['patient_id']
        
        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_data = cur.fetchone()
        
        final_hn = p_data['hn']
        final_gcn = p_data['gcn']
        
        # ถ้ายังเป็นเลขชั่วคราว (TMP) หรือยังไม่มีเลข ให้รันเลขจริง
        if not p_data['hn'] or str(p_data['hn']).startswith("TMP"):
            # 1. หาลำดับถัดไปจาก Supabase
            supabase = get_supabase_client()
            sb_res = supabase.table("patients").select("hn").execute()
            max_val = 0
            for r in sb_res.data:
                if r.get('hn'):
                    try:
                        num = int(str(r['hn']).upper().replace("HN", "").strip())
                        if num > max_val: max_val = num
                    except: continue
            
            final_hn = f"HN{(max_val + 1):03d}"
            
        if not p_data['gcn']:
            # 2. รันลำดับคิว (รีเซ็ตทุกวัน)
            cur.execute("SELECT COUNT(*) AS c FROM cga_headers WHERE status='completed' AND DATE(created_at) = CURDATE()")
            final_gcn = cur.fetchone()['c'] 
            
        # 3. บันทึกลง Supabase จริงๆ เพื่อให้เป็นทะเบียนหลัก
        # ทำเฉพาะถ้าเป็นเคสใหม่ (HN เดิมเป็น TMP หรือไม่มี)
        if not p_data['hn'] or str(p_data['hn']).startswith("TMP"):
            try:
                # สร้างที่อยู่แบบเต็มจากฟิลด์ที่แยกกัน
                assess_data = _get_assess_data(conn, header_id)
                full_addr_list = []
                if assess_data.get('house_no'): full_addr_list.append(f"บ้านเลขที่ {assess_data['house_no']}")
                if assess_data.get('moo'): full_addr_list.append(f"หมู่ที่ {assess_data['moo']}")
                if assess_data.get('subdistrict'): full_addr_list.append(f"ตำบล/แขวง {assess_data['subdistrict']}")
                if assess_data.get('district'): full_addr_list.append(f"อำเภอ/เขต {assess_data['district']}")
                if assess_data.get('province'): full_addr_list.append(f"จังหวัด {assess_data['province']}")
                if assess_data.get('postal_code'): full_addr_list.append(f"รหัสไปรษณีย์ {assess_data['postal_code']}")
                
                full_addr_str = " ".join(full_addr_list)

                final_hn_send = f"HN{next_hn_val:03d}" if 'next_hn_val' in locals() else p_data['hn']
                final_gcn_send = str(next_gcn).zfill(3) if 'next_gcn' in locals() else str(p_data['gcn']).zfill(3)
                
                sb_data = {
                    "hn": final_hn_send,
                    "gcn": final_gcn_send,
                    "full_name": str(p_data['full_name'] or "รอกรอกข้อมูล"),
                    "phone": str(p_data['phone'] or ""),
                    "address": full_addr_str or str(p_data.get('address_text') or p_data.get('address') or ""),
                    "caregiver_name": str(assess_data.get('caregiver_name') or ""),
                    "caregiver_relation": str(assess_data.get('caregiver_relation') or "")
                }
                if p_data.get('birth_date'): sb_data['birth_date'] = str(p_data['birth_date'])
                if p_data.get('sex'): sb_data['sex'] = str(p_data['sex'])
                if p_data.get('age_year'): 
                    try: sb_data['age_year'] = int(p_data['age_year'])
                    except: pass
                
                supabase.table("patients").insert(sb_data).execute()
            except Exception as sb_err:
                print("Supabase Sync Error:", sb_err)
                flash(f"Sync Cloud ล้มเหลว: {sb_err}", "warning")

        # 4. อัปเดต Local ให้ตรงกัน (พร้อมจัดการ Duplicate HN)
        try:
            cur.execute("UPDATE patients SET hn=%s, gcn=%s WHERE id=%s", (final_hn, final_gcn, p_id))
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                retry_count = 0
                while retry_count < 10:
                    retry_count += 1
                    # ดึงเลข Local สูงสุดมา + เพิ่ม
                    cur.execute("SELECT MAX(CAST(SUBSTRING(hn, 3) AS UNSIGNED)) as m FROM patients WHERE hn LIKE 'HN%'")
                    loc_max = cur.fetchone()['m'] or 0
                    
                    # ต้องมากกว่า max_val (จาก Supabase)
                    if 'max_val' not in locals(): max_val = loc_max # Fallback if local var missing
                    
                    new_num = max(loc_max, max_val) + retry_count
                    new_final_hn = f"HN{new_num:03d}"
                    try:
                        cur.execute("UPDATE patients SET hn=%s, gcn=%s WHERE id=%s", (new_final_hn, final_gcn, p_id))
                        # ถ้าสำเร็จ ให้อัปเดตเลขใหม่กลับไปที่ Supabase ด้วย (แก้ตัวเก่าที่เพิ่ง insert)
                        try:
                            supabase.table("patients").update({"hn": new_final_hn}).eq("hn", final_hn).execute() 
                        except: pass
                        break
                    except mysql.connector.Error:
                        continue

        conn.commit()
        if f.get('next_url'): return redirect(f.get('next_url'))
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
    except Exception as e:
        conn.rollback(); flash(f"Error: {e}", "danger"); return redirect(url_for('nurse.assess_tgds', header_id=header_id))
    finally: cur.close(); conn.close()

@nurse_bp.get('/assess/summary/<int:header_id>', endpoint='assess_summary')
def assess_summary(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection(); data = _get_assess_data(conn, header_id); cur = conn.cursor(dictionary=True, buffered=True)
    m_score = 0; cur.execute("SELECT total_score FROM assessment_mmse WHERE cga_id=%s", (header_id,)); m = cur.fetchone(); m_score = m['total_score'] if m else 0
    t_score = 0; cur.execute("SELECT total_score FROM assessment_tgds WHERE cga_id=%s", (header_id,)); t = cur.fetchone(); t_score = t['total_score'] if t else 0
    sr_val = 'none'; cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='suicideRisk'", (data.get('session_id'),)); sr = cur.fetchone(); sr_val = sr['answer_text'] if sr else 'none'
    inc_val = 'normal'; cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='incontinence'", (data.get('session_id'),)); ir = cur.fetchone(); inc_val = ir['answer_text'] if ir else 'normal'
    sl_val = 'normal'; cur.execute("SELECT answer_text FROM assessment_answers WHERE session_id=%s AND instrument='sleepProblems'", (data.get('session_id'),)); sr = cur.fetchone(); sl_val = sr['answer_text'] if sr else 'normal'
    cur.close(); conn.close()
    return render_template('nurse/summary.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), patient=data, date=date.today().strftime('%d/%m/%Y'), user={'name': session.get('full_name')}, mmse_score=m_score, mmse_risk=('normal' if m_score>23 else 'suspected'), tgds_score=t_score, tgds_risk=('normal' if t_score<5 else 'mild'), tgds_risk_label=('ปกติ' if t_score<5 else 'ซึมเศร้า'), suicide_risk=sr_val, incontinence=inc_val, sleep=sl_val)

@nurse_bp.get("/patients", endpoint="patients")
def patients():
    if not _require_nurse(): return redirect(url_for("auth.login"))
    search = request.args.get("search", "").strip()
    try:
        supabase = get_supabase_client()
        query = supabase.table("patients").select("*")
        if search:
            # ค้นหาแบบรวมในช่องเดียว: HN, GCN หรือ ชื่อ-นามสกุล
            query = query.or_(f"hn.ilike.%{search}%,gcn.ilike.%{search}%,full_name.ilike.%{search}%")
        
        response = query.order("id", desc=True).execute()
        rows = response.data
        # Format HN/GCN for display (HN001 style)
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

@nurse_bp.get("/patient/history/<int:patient_id>", endpoint="patient_history")
def patient_history(patient_id: int):
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # 1. ดึงข้อมูลพื้นฐานคนไข้
        cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
        patient = cur.fetchone()
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วย", "danger")
            return redirect(url_for("nurse.patients"))

        # 2. ดึงประวัติการประเมิน CGA ทั้งหมด
        query = """
            SELECT 
                h.id AS header_id,
                h.created_at,
                h.status,
                m.total_score AS mmse_score,
                t.total_score AS tgds_score
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id
            WHERE e.patient_id = %s
            ORDER BY h.created_at DESC
        """
        cur.execute(query, (patient_id,))
        history = cur.fetchall()

        return render_template("nurse/patient_history.html", patient=patient, history=history)
    finally:
        cur.close(); conn.close()

@nurse_bp.get("/patient/edit/<int:patient_id>", endpoint="patient_edit")
def patient_edit(patient_id: int):
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
        patient = cur.fetchone()
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วย", "danger")
            return redirect(url_for("nurse.patients"))
        return render_template("nurse/patient_edit.html", patient=patient)
    finally:
        cur.close(); conn.close()

@nurse_bp.post("/patient/update/<int:patient_id>", endpoint="patient_update")
def patient_update(patient_id: int):
    if not _require_nurse(): return redirect(url_for("auth.login"))
    f = request.form
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    try:
        # ตรวจสอบว่ามีคอลัมน์ address_text หรือ address
        cur.execute("SHOW COLUMNS FROM patients")
        cols = {r["Field"].lower() for r in cur.fetchall()}
        addr_col = "address_text" if "address_text" in cols else "address"
        bd_col = "birth_date" if "birth_date" in cols else "birthdate"
        sex_col = "sex" if "sex" in cols else "gender"
        age_col = "age_year" if "age_year" in cols else "age"

        # คำนวณอายุจากปีเกิด (ถ้ามีการแก้ไข)
        age_val = f.get('age')
        
        # แปลงข้อมูลเพศให้เป็นมาตรฐาน (male/female)
        sex_val = f.get('gender')
        if sex_val == 'ชาย': sex_val = 'male'
        elif sex_val == 'หญิง': sex_val = 'female'

        sql = f"""
            UPDATE patients SET 
                full_name = %s,
                phone = %s,
                {addr_col} = %s,
                {sex_col} = %s,
                {bd_col} = %s,
                {age_col} = %s
            WHERE id = %s
        """
        cur.execute(sql, (
            f.get('full_name'), 
            f.get('phone'), 
            f.get('address'), 
            sex_val,
            f.get('birthdate') or None, # รับค่า YYYY-MM-DD จากหน้าฟอร์ม
            age_val,
            patient_id
        ))
        conn.commit()
        flash("บันทึกการแก้ไขข้อมูลเรียบร้อยแล้ว", "success")
        return redirect(url_for("nurse.patients"))
    except Exception as e:
        conn.rollback(); flash(f"เกิดข้อผิดพลาด: {e}", "danger")
        return redirect(url_for("nurse.patient_edit", patient_id=patient_id))
    finally:
        cur.close(); conn.close()

@nurse_bp.post("/patient/delete/<int:patient_id>", endpoint="patient_delete")
def patient_delete(patient_id: int):
    if not _require_nurse(): return redirect(url_for("auth.login"))
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM patients WHERE id = %s", (patient_id,))
        conn.commit()
        flash("ลบข้อมูลผู้ป่วยเรียบร้อยแล้ว", "success")
    except Exception as e:
        conn.rollback(); flash(f"ไม่สามารถลบข้อมูลได้: {e}", "danger")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("nurse.patients"))