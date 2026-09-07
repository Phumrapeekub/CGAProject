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
    
    # ดึงข้อมูลจาก cga_records ใน Supabase แบบด่วนที่สุด
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if supabase_url and supabase_key:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            
            # ดึงข้อมูลดิบจาก cga_records
            res = supabase.table("cga_records").select("*").order("id", desc=True).limit(500).execute()
            if res.data:
                for r in res.data:
                    # กรองค้นหาแบบง่าย
                    if q and q.lower() not in (r.get("full_name") or "").lower() and q.lower() not in (r.get("hn") or "").lower():
                        continue
                        
                    scores = []
                    if r.get("mmse_score") is not None: scores.append({"instrument": "MMSE", "total_score": r["mmse_score"]})
                    if r.get("tgds_score") is not None: scores.append({"instrument": "TGDS", "total_score": r["tgds_score"]})
                    
                    assesses.append({
                        "header_id": r.get("id"),
                        "assessment_date": r.get("assessed_date") or r.get("created_at", "")[:10],
                        "hn": r.get("hn"),
                        "full_name": r.get("full_name") or "ไม่ระบุชื่อ",
                        "scores": scores,
                        "status_label": "สมบูรณ์",
                        "status_color": "green"
                    })
    except Exception as e:
        print(f"Supabase Fetch Error: {e}")

    # Fallback สุดท้าย: ถ้า Cloud ไม่มา ให้ดึงจาก MySQL ตารางที่นำเข้า CSV
    if not assesses:
        try:
            from db.db import get_db_connection
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM stg_cga_csv ORDER BY id DESC LIMIT 500")
                for r in cur.fetchall():
                    if q and q.lower() not in (r.get("first_name") or "").lower() and q.lower() not in (r.get("hn") or "").lower():
                        continue
                    assesses.append({
                        "header_id": r["id"],
                        "assessment_date": r.get("assessed_date_text") or "-",
                        "hn": r["hn"],
                        "full_name": f"{r.get('first_name','')} {r.get('last_name','')}",
                        "scores": [{"instrument": "MMSE", "total_score": r.get("mmse_score")}],
                        "status_label": "สมบูรณ์",
                        "status_color": "green"
                    })
                cur.close(); conn.close()
        except: pass

    total_count = len(assesses)
    return render_template("admin/assessments.html", assessments=assesses[offset:offset+per_page], active_page="assessments", q=q, page=page, total_pages=max(1, (total_count+per_page-1)//per_page), total_count=total_count, target_patient_id=None, start_date=None, end_date=None)

"""
    new_content = content[:start_idx] + new_func + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully fixed assessments_list to pull from cga_records")

if __name__ == "__main__":
    fix()
