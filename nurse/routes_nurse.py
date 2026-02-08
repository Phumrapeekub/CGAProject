from __future__ import annotations
from datetime import date, datetime
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
        
        cur.execute("SELECT * FROM patients WHERE id = %s", (p_id,))
        p_row = cur.fetchone()
        if not p_row: return {"hn": "N/A", "gcn": "N/A"}
        
        cur.execute("SHOW COLUMNS FROM patients")
        p_cols = {r["Field"].lower() for r in cur.fetchall()}
        bd_col = "birth_date" if "birth_date" in p_cols else ("birthdate" if "birthdate" in p_cols else None)
        sex_col = "sex" if "sex" in p_cols else ("gender" if "gender" in p_cols else None)
        addr_col = "address_text" if "address_text" in p_cols else ("address" if "address" in p_cols else None)
        age_col = "age_year" if "age_year" in p_cols else ("age" if "age" in p_cols else None)

        res = {
            "hn": _get_val(p_row, "hn"),
            "gcn": _get_val(p_row, "gcn"),
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
        return res
    except: return {"hn": "N/A", "gcn": "N/A"}
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

        query = """
            SELECT 
                h.id AS header_id, p.hn, p.full_name, 
                m.total_score AS mmse_score, 
                t.total_score AS tgds_score,
                h.created_at
            FROM cga_headers h
            JOIN encounters e ON e.id = h.encounter_id
            JOIN patients p ON p.id = e.patient_id
            LEFT JOIN assessment_mmse m ON m.cga_id = h.id
            LEFT JOIN assessment_tgds t ON t.cga_id = h.id
            WHERE h.status = 'completed'
            ORDER BY h.created_at DESC
            LIMIT 5
        """
        cur.execute(query)
        recent_patients = cur.fetchall()
    except: pass
    finally:
        cur.close(); conn.close()
    return render_template("nurse/dashboard.html", kpis=kpis, recent_patients=recent_patients, user=session.get("username"), role="พยาบาล")

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
        cur.execute("SELECT COUNT(*) AS c FROM encounters WHERE encounter_date = CURDATE()"); gcn_num = cur.fetchone()["c"] + 1
        cur.execute("SELECT COUNT(*) AS c FROM patients"); hn_num = cur.fetchone()["c"] + 1
        new_hn, new_gcn = f"{hn_num:07d}", f"{gcn_num:03d}"
        cur.execute("INSERT INTO patients (hn, gcn, full_name) VALUES (%s, %s, 'รอกรอกข้อมูล')", (new_hn, new_gcn)); p_id = cur.lastrowid
        cur.execute("INSERT INTO encounters (patient_id, encounter_date, created_by) VALUES (%s, CURDATE(), %s)", (p_id, session.get("user_id"))); enc_id = cur.lastrowid
        cur.execute("INSERT INTO assessment_sessions (encounter_id, session_type, created_by) VALUES (%s, 'baseline', %s)", (enc_id, session.get("user_id"))); sess_id = cur.lastrowid
        try: cur.execute("INSERT INTO cga_headers (encounter_id, session_id, created_at, status) VALUES (%s, %s, NOW(), 'in_progress')", (enc_id, sess_id))
        except: 
            cur.execute("ALTER TABLE cga_headers ADD COLUMN status ENUM('in_progress','completed') DEFAULT 'in_progress'")
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
            fields = ['marry', 'live', 'smoke', 'alcohol', 'hearing_left', 'hearing_right', 'visionTest', 'height', 'weight', 'waist', 'otherDisease', 'age']
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
    conn = get_db_connection(); cur = conn.cursor(dictionary=True, buffered=True)
    cur.execute("SELECT * FROM patients ORDER BY id DESC LIMIT 50"); rows = cur.fetchall(); cur.close(); conn.close()
    return render_template("nurse/patients.html", patients=rows)

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