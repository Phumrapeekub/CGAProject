import os

def fix():
    path = 'admin/routes_admin.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    start_marker = '@admin_bp.get("/assessments")'
    end_marker = '@admin_bp.get("/assessments/<int:header_id>")'
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx == -1 or end_idx == -1:
        print("Error: Could not find markers")
        return

    new_func = """@admin_bp.get("/assessments")
def assessments_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    q = (request.args.get("q") or "").strip()
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    assesses = []
    
    try:
        from db.db import get_db_connection
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            # 1. ดึงรายชื่อคนไข้เป็นหลัก
            sql_p = "SELECT hn, full_name FROM patients"
            if q: sql_p += " WHERE hn LIKE %s OR full_name LIKE %s"
            sql_p += " ORDER BY id DESC LIMIT 500"
            cur.execute(sql_p, (f"%{q}%", f"%{q}%") if q else ())
            patients = cur.fetchall()
            
            # 2. ดึงประวัติ
            cur.execute("SELECT * FROM stg_cga_csv")
            history = {h['hn']: h for h in cur.fetchall()}
            
            # 3. ดึง sessions
            cur.execute("SELECT s.id, s.created_at, p.hn FROM assessment_sessions s JOIN encounters e ON s.encounter_id = e.id JOIN patients p ON e.patient_id = p.id")
            sessions = {s['hn']: s for s in cur.fetchall()}
            
            for p in patients:
                hn = p['hn']
                h = history.get(hn)
                s = sessions.get(hn)
                if h or s:
                    date_val = str(s['created_at'])[:10] if s else (h['assessed_date_text'] if h else "-")
                    scores = []
                    if h:
                        if h.get('mmse_score'): scores.append({"instrument": "MMSE", "total_score": h['mmse_score']})
                        if h.get('tgds_score'): scores.append({"instrument": "TGDS", "total_score": h['tgds_score']})
                    assesses.append({
                        "header_id": s['id'] if s else (h['id'] if h else 0),
                        "assessment_date": date_val,
                        "hn": hn, "full_name": p['full_name'],
                        "scores": scores, "status_label": "สมบูรณ์" if h else "กำลังประเมิน",
                        "status_color": "green" if h else "orange"
                    })
            cur.close(); conn.close()
    except Exception as e: print(f"Error: {e}")

    total_count = len(assesses)
    return render_template("admin/assessments.html", assessments=assesses[offset:offset+per_page], active_page="assessments", q=q, page=page, total_pages=max(1, total_count//per_page), total_count=total_count, target_patient_id=None, start_date=None, end_date=None)

"""
    new_content = content[:start_idx] + new_func + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully fixed assessments_list")

if __name__ == "__main__":
    fix()
