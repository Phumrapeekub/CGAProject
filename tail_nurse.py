@nurse_bp.post('/assess/step1/save/<int:header_id>', endpoint='assess_step1_save')
def assess_step1_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    name = (request.form.get('name') or "").strip()
    surname = (request.form.get('surname') or "").strip()
    birthdate = (request.form.get('birthdate') or "").strip()
    gender = (request.form.get('gender') or "").strip()
    full_name = f'{name} {surname}'.strip()

    conn = get_db_connection()
    if not conn:
        flash("เชื่อมต่อฐานข้อมูลไม่สำเร็จ", "danger")
        return redirect(url_for('nurse.assess_session', header_id=header_id))
        
    cur = conn.cursor(dictionary=True)
    try:
        hdr_table, hdr_enc_fk, *_ = _find_headers_table(conn)
        patient_table, patient_id_col, *_ = _find_patient_table(conn)
        enc_table, enc_patient_fk, *_ = _find_encounter_table(conn, patient_table)

        cur.execute(f"SELECT {hdr_enc_fk} FROM {hdr_table} WHERE id = %s", (header_id,))
        h_row = cur.fetchone()
        enc_id = _get_val(h_row, hdr_enc_fk)
        
        cur.execute(f"SELECT {enc_patient_fk} FROM {enc_table} WHERE id = %s", (enc_id,))
        p_id = _get_val(cur.fetchone(), enc_patient_fk)

        cur.execute(f"SHOW COLUMNS FROM {patient_table}")
        p_cols = {r["Field"].lower() for r in cur.fetchall()}
        sex_col = "sex" if "sex" in p_cols else "gender"
        bd_col = "birth_date" if "birth_date" in p_cols else "birthdate"

        db_gender = None
        if gender == 'male': db_gender = 'ชาย' if sex_col == 'sex' else 'male'
        elif gender == 'female': db_gender = 'หญิง' if sex_col == 'sex' else 'female'

        upd_parts = [f"full_name = %s", f"{bd_col} = %s", f"{sex_col} = %s"]
        params = [full_name, birthdate if birthdate else None, db_gender]
        if 'first_name' in p_cols:
            upd_parts.append("first_name = %s")
            params.append(name)
        if 'last_name' in p_cols:
            upd_parts.append("last_name = %s")
            params.append(surname)
        
        params.append(p_id)
        cur.execute(f"UPDATE {patient_table} SET {', '.join(upd_parts)} WHERE {patient_id_col} = %s", tuple(params))
        conn.commit()
        flash('บันทึกข้อมูลทั่วไปสำเร็จ', 'success')
        return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_session', header_id=header_id))
    finally:
        cur.close()
        conn.close()

def _get_assess_data(conn, header_id):
    """Helper ดึงข้อมูลผู้ป่วยแบบเจาะลึก เพื่อให้มั่นใจว่าข้อมูลไม่หาย"""
    cur = conn.cursor(dictionary=True)
    try:
        patient_table, patient_id_col, hn_col, gcn_col = _find_patient_table(conn)
        hdr_table, hdr_enc_fk, *_ = _find_headers_table(conn)
        enc_table, enc_patient_fk, *_ = _find_encounter_table(conn, patient_table)

        cur.execute(f"SHOW COLUMNS FROM {patient_table}")
        p_cols = {r["Field"].lower() for r in cur.fetchall()}
        sex_col = "sex" if "sex" in p_cols else "gender"
        bd_col = "birth_date" if "birth_date" in p_cols else "birthdate"

        cur.execute(f"SELECT {hdr_enc_fk} FROM {hdr_table} WHERE id = %s", (header_id,))
        h_row = cur.fetchone()
        enc_id = _get_val(h_row, hdr_enc_fk)
        
        cur.execute(f"SELECT {enc_patient_fk} FROM {enc_table} WHERE id = %s", (enc_id,))
        p_id = _get_val(cur.fetchone(), enc_patient_fk)
        
        cur.execute(f"SELECT * FROM {patient_table} WHERE {patient_id_col} = %s", (p_id,))
        p_row = cur.fetchone()
        
        if p_row:
            fname = _get_val(p_row, "full_name")
            if (not fname or fname == 'รอกรอกข้อมูล') and 'first_name' in p_cols:
                fname = f"{_get_val(p_row, 'first_name')} {_get_val(p_row, 'last_name', '')}".strip()

            return {
                "hn": _get_val(p_row, hn_col),
                "gcn": _get_val(p_row, gcn_col),
                "full_name": fname,
                "birth_date": _get_val(p_row, bd_col),
                "gender": _get_val(p_row, sex_col),
                "patient_id": p_id
            }
    except: pass
    return {"hn": "N/A", "gcn": "N/A"}

def _get_answers(conn, header_id, instrument):
    """ดึงคำตอบเดิมที่เคยบันทึกไว้"""
    cur = conn.cursor(dictionary=True)
    table = f"assessment_{instrument}_items"
    header_table = f"assessment_{instrument}"
    try:
        cur.execute(f"SHOW TABLES LIKE '{header_table}'")
        if not cur.fetchone(): return {}
        cur.execute(f"SELECT id FROM {header_table} WHERE cga_id = %s", (header_id,))
        h = cur.fetchone()
        if not h: return {}
        cur.execute(f"SHOW COLUMNS FROM {table}")
        cols = {r['Field'].lower() for r in cur.fetchall()}
        val_col = "answer" if "answer" in cols else ("answer_text" if "answer_text" in cols else "score")
        cur.execute(f"SELECT question_no, score, {val_col} as val FROM {table} WHERE {instrument}_id = %s", (h['id'],))
        rows = cur.fetchall()
        return {r['question_no']: r for r in rows}
    except: return {}

@nurse_bp.get('/assess/mmse/<int:header_id>', endpoint='assess_mmse')
def assess_mmse(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    data = _get_assess_data(conn, header_id)
    answers = _get_answers(conn, header_id, 'mmse')
    conn.close()
    return render_template('nurse/mmse.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), answers=answers)

@nurse_bp.post('/assess/mmse/save/<int:header_id>', endpoint='assess_mmse_save')
def assess_mmse_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO assessment_mmse (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_mmse WHERE cga_id = %s", (header_id,))
        mmse_id = cur.fetchone()[0]
        total_score = 0
        cur.execute("DELETE FROM assessment_mmse_items WHERE mmse_id = %s", (mmse_id,))
        for key, val in request.form.items():
            if key.startswith('q'):
                try:
                    q_no = int(key[1:])
                    score = int(val) if val.isdigit() else 0
                    total_score += score
                    cur.execute("INSERT INTO assessment_mmse_items (mmse_id, question_no, score) VALUES (%s, %s, %s)", (mmse_id, q_no, score))
                except: continue
        cur.execute("UPDATE assessment_mmse SET total_score = %s WHERE id = %s", (total_score, mmse_id))
        conn.commit()
        return redirect(url_for('nurse.assess_tgds', header_id=header_id))
    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_mmse', header_id=header_id))
    finally:
        conn.close()

@nurse_bp.get('/assess/tgds/<int:header_id>', endpoint='assess_tgds')
def assess_tgds(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    data = _get_assess_data(conn, header_id)
    answers = _get_answers(conn, header_id, 'tgds')
    conn.close()
    return render_template('nurse/tgds15.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), answers=answers)

@nurse_bp.post('/assess/tgds/save/<int:header_id>', endpoint='assess_tgds_save')
def assess_tgds_save(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO assessment_tgds (cga_id) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", (header_id,))
        cur.execute("SELECT id FROM assessment_tgds WHERE cga_id = %s", (header_id,))
        tgds_id = cur.fetchone()[0]
        total_score = 0
        cur.execute("DELETE FROM assessment_tgds_items WHERE tgds_id = %s", (tgds_id,))
        for key, val in request.form.items():
            if key.startswith('q'):
                try:
                    q_no = int(key[1:])
                    score = 1 if val == 'yes' else 0
                    total_score += score
                    cur.execute("INSERT INTO assessment_tgds_items (tgds_id, question_no, answer, score) VALUES (%s, %s, %s, %s)", (tgds_id, q_no, 1 if val=='yes' else 0, score))
                except: continue
        cur.execute("UPDATE assessment_tgds SET total_score = %s WHERE id = %s", (total_score, tgds_id))
        conn.commit()
        return redirect(url_for('nurse.assess_summary', header_id=header_id))
    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error: {e}", "danger")
        return redirect(url_for('nurse.assess_tgds', header_id=header_id))
    finally:
        conn.close()

@nurse_bp.get('/assess/8q/<int:header_id>', endpoint='assess_8q')
def assess_8q(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    data = _get_assess_data(conn, header_id)
    conn.close()
    return render_template('nurse/next_placeholder.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"), title='8Q')

@nurse_bp.get('/assess/summary/<int:header_id>', endpoint='assess_summary')
def assess_summary(header_id: int):
    if not _require_nurse(): return redirect(url_for('auth.login'))
    conn = get_db_connection()
    data = _get_assess_data(conn, header_id)
    conn.close()
    return render_template('nurse/summary.html', header_id=header_id, hn=data.get("hn"), gcn=data.get("gcn"))
