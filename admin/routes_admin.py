from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from werkzeug.security import generate_password_hash
from db.db import get_db_connection
from supabase import create_client, Client
import os
from datetime import date, datetime, timedelta
import calendar
from mysql.connector import Error as MySQLdbError

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

def _require_admin():
    return (
        session.get("logged_in")
        and session.get("role") == "admin"
        and session.get("user_id")
    )

@admin_bp.route("/dashboard")
def dashboard():
    if not _require_admin():
        return redirect(url_for("auth.login"))

    today_obj = date.today()
    selected_month = int(request.args.get("month", today_obj.month))
    selected_year = int(request.args.get("year", today_obj.year))
    
    if not (1 <= selected_month <= 12) or not (2000 <= selected_year <= today_obj.year + 5):
        selected_month = today_obj.month
        selected_year = today_obj.year

    conn = None
    cur = None
    stats = {"users": 0, "patients": 0, "today_patients": 0, "appointments_today": 0, "assessments_today": 0, "total_assessments": 0}
    latest_users = []
    patient_day_labels = []
    patient_day_values = []
    service_type_labels = []
    service_type_values = []

    # Supabase Client Initialization
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    supabase_client = None
    if supabase_url and supabase_key:
        try:
            supabase_client = create_client(supabase_url, supabase_key)
        except Exception as e:
            print(f"Dashboard Supabase Init Error: {e}")

    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS count FROM users")
            stats["users"] = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM appointments WHERE DATE(appt_datetime) = CURDATE()")
            stats["appointments_today"] = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM assessment_sessions WHERE DATE(created_at) = CURDATE()")
            stats["assessments_today"] = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM assessment_sessions")
            stats["total_assessments"] = cur.fetchone()["count"]
            
            # Fetch from MySQL first as initial data
            cur.execute("SELECT username, role, created_at FROM users ORDER BY created_at DESC LIMIT 5")
            latest_users_raw = cur.fetchall()
            latest_users = []
            for u in latest_users_raw:
                display_date = "-"
                if u.get("created_at") and isinstance(u["created_at"], datetime):
                    display_date = u["created_at"].strftime('%d/%m/%Y %H:%M')
                latest_users.append({
                    "username": u["username"],
                    "role": u["role"],
                    "created_at_display": display_date
                })

            # 1. Fetch Service Type counts (Followup & CGA)
            cur.execute("SELECT appt_type, COUNT(*) AS count FROM appointments WHERE appt_type IN ('followup', 'cga') GROUP BY appt_type")
            service_type_data = cur.fetchall()
            
            # 2. Fetch Today's Scheduled Appointments Count
            cur.execute("SELECT COUNT(*) AS count FROM appointments WHERE DATE(appt_datetime) = CURDATE() AND status = 'scheduled'")
            today_appt_count = cur.fetchone()["count"]
            
            # Map DB ENUM values to Display Labels
            mapping = {
                "followup": "ติดตามอาการ",
                "cga": "ประเมิน CGA"
            }
            temp_dict = {label: 0 for label in mapping.values()}
            for row in service_type_data:
                db_val = row["appt_type"]
                if db_val in mapping:
                    temp_dict[mapping[db_val]] = row["count"]
            
            # Add Today's Appointments to the chart data
            service_type_labels = list(temp_dict.keys())
            service_type_values = list(temp_dict.values())
            
            service_type_labels.append("นัดหมายวันนี้")
            service_type_values.append(today_appt_count)
            
            # Fallback: If no data at all, show sample data for visualization
            if sum(service_type_values) == 0:
                service_type_labels = ["ติดตามอาการ", "ประเมิน CGA", "นัดหมายวันนี้"]
                service_type_values = [10, 8, 5]

        if supabase_client:
            try:
                # 1. Total Patients
                res_total = supabase_client.table("patients").select("id", count="exact").execute()
                stats["patients"] = res_total.count or 0
                
                # 2. Today's Patients
                start_of_today = datetime.combine(today_obj, datetime.min.time()).isoformat()
                res_today = supabase_client.table("patients").select("id", count="exact").gte("created_at", start_of_today).execute()
                stats["today_patients"] = res_today.count or 0

                # 3. Latest Users
                res_users = supabase_client.table("users").select("username, role, created_at").order("created_at", desc=True).limit(5).execute()
                if res_users.data:
                    latest_users = []
                    for u in res_users.data:
                        display_date = "-"
                        if u.get("created_at"):
                            try:
                                dt = datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
                                display_date = dt.strftime('%d/%m/%Y %H:%M')
                            except: display_date = u["created_at"]
                        latest_users.append({"username": u["username"], "role": u["role"], "created_at_display": display_date})

                # 4. Patient Chart (New Patients per Day - MONTHLY)
                # Fetch all patients for the selected month in ONE query
                first_day = date(selected_year, selected_month, 1)
                last_day_num = calendar.monthrange(selected_year, selected_month)[1]
                last_day = date(selected_year, selected_month, last_day_num)
                
                res_month = supabase_client.table("patients").select("created_at")\
                    .gte("created_at", first_day.isoformat())\
                    .lte("created_at", datetime.combine(last_day, datetime.max.time()).isoformat())\
                    .execute()
                
                # Aggregate in Python
                day_counts = {day: 0 for day in range(1, last_day_num + 1)}
                for p in (res_month.data or []):
                    try:
                        dt = datetime.fromisoformat(p['created_at'].split('T')[0])
                        if dt.month == selected_month:
                            day_counts[dt.day] += 1
                    except: pass
                
                patient_day_labels = [f"{d}/{selected_month}" for d in range(1, last_day_num + 1)]
                patient_day_values = [day_counts[d] for d in range(1, last_day_num + 1)]

                # 5. Service Type Chart (Real Data from CGA Records & Consultations)
                res_cga = supabase_client.table("cga_records").select("id", count="exact").execute()
                res_cons = supabase_client.table("consultations").select("id", count="exact").execute()
                
                service_type_labels = ["ประเมินสำเร็จ (CGA)", "รอสรุป (Referral)"]
                service_type_values = [res_cga.count or 0, res_cons.count or 0]
                
                # If everything is zero, show placeholders so chart isn't empty
                if sum(service_type_values) == 0:
                    service_type_values = [1, 1] # Just for UI visibility

            except Exception as e:
                print(f"Dashboard Supabase Logic Error: {e}")
                if cur:
                    cur.execute("SELECT COUNT(*) AS count FROM patients")
                    stats["patients"] = cur.fetchone()["count"]
                    cur.execute("SELECT COUNT(*) AS count FROM patients WHERE DATE(created_at) = CURDATE()")
                    stats["today_patients"] = cur.fetchone()["count"]
        elif cur:
            cur.execute("SELECT COUNT(*) AS count FROM patients")
            stats["patients"] = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM patients WHERE DATE(created_at) = CURDATE()")
            stats["today_patients"] = cur.fetchone()["count"]

    except Exception as e:
        print(f"Admin Dashboard Error: {e}")
        flash(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}", "error")
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return render_template(
        "admin/dashboard.html",
        today=today_obj,
        username=session.get("username"),
        stats=stats,
        latest_users=latest_users,
        patient_day_labels=patient_day_labels,
        patient_day_values=patient_day_values,
        service_type_labels=service_type_labels,
        service_type_values=service_type_values,
        selected_month=selected_month,
        selected_year=selected_year,
        active_page="dashboard",
    )

@admin_bp.get("/next-hn")
def get_next_hn():
    if not _require_admin():
        return {"error": "Unauthorized"}, 401
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    next_num = 1
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            # Get all HNs starting with 'HN' to find the maximum
            response = supabase.table("patients").select("hn").like("hn", "HN%").execute()
            
            if response.data:
                nums = []
                for item in response.data:
                    val = item.get("hn", "")
                    if val and val.startswith("HN"):
                        try:
                            # Extract numeric part
                            n = int(val[2:])
                            nums.append(n)
                        except:
                            continue
                if nums:
                    next_num = max(nums) + 1
        else:
            # Fallback to MySQL
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT hn FROM patients WHERE hn LIKE 'HN%'")
                rows = cur.fetchall()
                nums = []
                for (val,) in rows:
                    try:
                        n = int(val[2:])
                        nums.append(n)
                    except:
                        continue
                if nums:
                    next_num = max(nums) + 1
                cur.close()
                conn.close()

        return {"hn": f"HN{next_num:03d}"}
    except Exception as e:
        print(f"Error fetching next HN: {e}")
        return {"hn": "HN001"}

@admin_bp.get("/patients")
def patients_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    q = (request.args.get("q") or "").strip()
    filter_type = request.args.get("filter")
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        flash("Supabase configuration missing", "error")
        return render_template("admin/patients.html", patients=[], q=q, page=1, total_pages=1, active_page="patients")
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        # Revert to simple query to ensure list shows up. 
        # Complex nested query might be failing due to relation names or permissions.
        query = supabase.table("patients").select("*", count="exact")
        
        if q: 
            query = query.or_(f"full_name.ilike.%{q}%,hn.ilike.%{q}%")
        
        if filter_type == "today":
            today_str = date.today().isoformat()
            query = query.gte("created_at", today_str)

        resp = query.order("created_at", desc=True).range(offset, offset + per_page - 1).execute()
        patients_data = resp.data
        total_rows = resp.count or 0
        total_pages = max((total_rows + per_page - 1) // per_page, 1)
        
        # Fetch patient HNs who already have assessments
        assessed_hns = set()
        try:
            current_hns = [p['hn'] for p in patients_data if p.get('hn')]
            if current_hns:
                # 1. Check cga_records by HN
                rec_resp = supabase.table("cga_records").select("hn").in_("hn", current_hns).execute()
                for r in rec_resp.data:
                    if r.get('hn'): assessed_hns.add(r['hn'])
                
                # 2. Check consultations by HN
                cons_resp = supabase.table("consultations").select("hn").in_("hn", current_hns).execute()
                for c in cons_resp.data:
                    if c.get('hn'): assessed_hns.add(c['hn'])

        except Exception as e:
            print(f"Error checking assessed patients by HN: {e}")

        # Process patients
        for p in patients_data:
            hn = p.get('hn')
            if hn and hn in assessed_hns:
                p['risk_status'] = 'ประเมินเสร็จสิ้น'
                p['risk_color'] = 'green'
            else:
                p['risk_status'] = 'รอประเมิน'
                p['risk_color'] = 'slate'

        return render_template("admin/patients.html", patients=patients_data, q=q, filter=filter_type, page=page, total_pages=total_pages, total_rows=total_rows, active_page="patients")
    except Exception as e:
        print(f"Admin Patients Supabase Error: {e}")
        flash(f"เกิดข้อผิดพลาดในการโหลดข้อมูลจาก Supabase: {e}", "error")
        return render_template("admin/patients.html", patients=[], q=q, page=1, total_pages=1, active_page="patients")

@admin_bp.post("/patients/add")
def add_patient():
    if not _require_admin(): return redirect(url_for("auth.login"))
    form_created_at = request.form.get("created_at")
    now = datetime.now()
    created_at_val = form_created_at if form_created_at else now.isoformat()
    
    data = {
        "hn": (request.form.get("hn") or "").strip(),
        "full_name": (request.form.get("full_name") or "").strip(),
        "gender": (request.form.get("gender") or "").strip(),
        "birth_date": request.form.get("birth_date") or None,
        "phone": (request.form.get("phone") or "").strip(),
        "address": (request.form.get("address") or "").strip(),
        "created_at": created_at_val,
        "updated_at": created_at_val,
    }
    if not data["hn"] or not data["full_name"]:
        flash("กรุณากรอก HN และชื่อเต็มของผู้ป่วย", "error")
        return redirect(url_for("admin.patients_list"))
    try:
        # 1. ALWAYS Save to Local MySQL First (The safety net)
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO patients (hn, full_name, gender, birth_date, phone, address, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data["hn"], data["full_name"], data["gender"], data["birth_date"], data["phone"], data["address"], data["created_at"]))
            conn.commit()
            cur.close(); conn.close()
            print("✅ Data saved to Local MySQL successfully.")
    except Exception as e:
        print(f"❌ Local MySQL Error: {e}")
        flash(f"ข้อผิดพลาดฐานข้อมูลในเครื่อง: {e}", "error")
        return redirect(url_for("admin.patients_list"))

    # 2. Try Supabase (Internet dependent)
    try:
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            supabase_data = {
                "hn": data["hn"],
                "full_name": data["full_name"],
                "gender": data["gender"],
                "birth_date": data["birth_date"],
                "phone": data["phone"],
                "address": data["address"],
                "created_at": data["created_at"]
            }
            supabase.table("patients").insert(supabase_data).execute()
            flash("เพิ่มข้อมูลผู้ป่วยและซิงค์ข้อมูลสำเร็จ", "success")
        else:
            flash("บันทึกข้อมูลในเครื่องสำเร็จ (ยังไม่ได้ตั้งค่า Cloud)", "info")
    except Exception as e:
        # INTERNET DISCONNECTED CASE
        print(f"⚠️ Cloud Sync Failed (Internet?): {e}")
        flash("บันทึกข้อมูลในเครื่องสำเร็จแล้ว! (ระบบจะซิงค์ขึ้น Cloud ภายหลังเมื่อเน็ตกลับมาปกติ)", "warning")
    
    return redirect(url_for("admin.patients_list"))

@admin_bp.post("/patients/delete/<int:id>")
def delete_patient(id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    try:
        # 1. Handle Supabase Deletion
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            
            # Get encounter IDs for this patient
            enc_resp = supabase.table("encounters").select("id").eq("patient_id", id).execute()
            enc_ids = [e['id'] for e in enc_resp.data]
            
            if enc_ids:
                # Get CGA header IDs
                cga_resp = supabase.table("cga_headers").select("id").in_("encounter_id", enc_ids).execute()
                cga_ids = [c['id'] for c in cga_resp.data]
                
                # Delete sub-records first
                if cga_ids:
                    supabase.table("assessment_scores").delete().in_("cga_id", cga_ids).execute()
                    supabase.table("cga_headers").delete().in_("id", cga_ids).execute()
                
                supabase.table("assessment_sessions").delete().in_("encounter_id", enc_ids).execute()
                supabase.table("encounters").delete().eq("patient_id", id).execute()
            
            # Delete appointments
            supabase.table("appointments").delete().eq("patient_id", id).execute()
            
            # Finally delete the patient
            supabase.table("patients").delete().eq("id", id).execute()

        # 2. Handle MySQL Deletion (Sync)
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            # We use cascaded deletes or manual cleanup here too if needed
            # For simplicity and safety, we follow the same chain:
            # (Assumes standard schema where ID is the primary key)
            
            cur.execute("DELETE FROM assessment_scores WHERE cga_id IN (SELECT id FROM cga_headers WHERE encounter_id IN (SELECT id FROM encounters WHERE patient_id = %s))", (id,))
            cur.execute("DELETE FROM cga_headers WHERE encounter_id IN (SELECT id FROM encounters WHERE patient_id = %s)", (id,))
            cur.execute("DELETE FROM assessment_sessions WHERE encounter_id IN (SELECT id FROM encounters WHERE patient_id = %s)", (id,))
            cur.execute("DELETE FROM appointments WHERE patient_id = %s", (id,))
            cur.execute("DELETE FROM encounters WHERE patient_id = %s", (id,))
            cur.execute("DELETE FROM patients WHERE id = %s", (id,))
            
            conn.commit()
            cur.close(); conn.close()

        flash("ลบข้อมูลผู้ป่วยและประวัติที่เกี่ยวข้องเรียบร้อยแล้ว", "success")
    except Exception as e:
        print(f"Error deleting patient: {e}")
        flash(f"เกิดข้อผิดพลาดในการลบข้อมูล: {e}", "error")
        
    return redirect(url_for("admin.patients_list"))

@admin_bp.get("/patients/<int:id>")
def patient_detail(id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        flash("Supabase configuration missing", "error")
        return redirect(url_for("admin.patients_list"))
        
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Fetch patient
        resp = supabase.table("patients").select("*").eq("id", id).execute()
        if not resp.data:
            flash("ไม่พบข้อมูลผู้ป่วย", "error")
            return redirect(url_for("admin.patients_list"))
        patient = resp.data[0]
        
        # Fetch primary doctor info if exists
        primary_doctor = None
        if patient.get("primary_doctor_id"):
            try:
                doc_resp = supabase.table("users").select("id, full_name, username").eq("id", patient["primary_doctor_id"]).single().execute()
                primary_doctor = doc_resp.data
            except:
                pass

        # Fetch all doctors for dropdown (in case they want to change it)
        try:
            all_docs_resp = supabase.table("users").select("id, full_name").eq("role", "doctor").execute()
            doctors = all_docs_resp.data
        except:
            doctors = []
        
        # Get patient assessments history using HN as primary link
        assessments = []
        chart_data = {"labels": [], "mmse": [], "tgds": []}
        
        try:
            print(f"DEBUG: Fetching history for HN: {patient['hn']}")
            
            # --- 1. Fetch from cga_records (Historical/Imported) ---
            history_resp = supabase.table("cga_records").select("*").eq("hn", patient["hn"]).order("assessed_date").execute()
            if history_resp.data:
                for r in history_resp.data:
                    d_str = r.get("assessed_date") or "-"
                    assessments.append({
                        "header_id": r["id"],
                        "date": d_str,
                        "risk": r.get("mmse_result") or "N/A",
                        "status": "สมบูรณ์",
                        "mmse_score": r.get("mmse_score"),
                        "tgds_score": r.get("tgds_score"),
                        "source": "cga_records"
                    })

            # --- 2. Fetch from consultations (Referral System) ---
            cons_resp = supabase.table("consultations").select("*").eq("hn", patient["hn"]).order("created_at").execute()
            if cons_resp.data:
                for c in cons_resp.data:
                    c_date = c.get("created_at")[:10] if c.get("created_at") else "-"
                    assessments.append({
                        "header_id": c.get("id"),
                        "date": c_date,
                        "risk": c.get("diagnosis") or "วินิจฉัยแล้ว",
                        "status": "สมบูรณ์",
                        "mmse_score": c.get("mmse_score"),
                        "tgds_score": c.get("tgds_score"),
                        "source": "consultations"
                    })

            # --- 3. Fetch from Systemic Tables (cga_headers + assessment_scores) ---
            try:
                # Get encounters for this patient
                enc_resp = supabase.table("encounters").select("id, encounter_date").eq("patient_id", id).execute()
                if enc_resp.data:
                    enc_ids = [e['id'] for e in enc_resp.data]
                    enc_map = {e['id']: e['encounter_date'] for e in enc_resp.data}
                    
                    # Get CGA headers
                    headers_resp = supabase.table("cga_headers")\
                        .select("id, assessed_at, overall_risk, encounter_id, assessment_sessions(id, status)")\
                        .in_("encounter_id", enc_ids)\
                        .execute()
                    
                    if headers_resp.data:
                        header_ids = [h['id'] for h in headers_resp.data]
                        
                        # Get Scores for these headers
                        scores_resp = supabase.table("assessment_scores")\
                            .select("cga_id, instrument, total_score")\
                            .in_("cga_id", header_ids)\
                            .execute()
                        
                        scores_map = {}
                        for s in scores_resp.data:
                            cid = s['cga_id']
                            if cid not in scores_map: scores_map[cid] = {}
                            scores_map[cid][s['instrument'].lower()] = s['total_score']

                        for h in headers_resp.data:
                            sess = h.get("assessment_sessions") or []
                            if isinstance(sess, list) and sess: sess = sess[0]
                            elif isinstance(sess, dict): pass
                            else: sess = {}
                            
                            cid = h['id']
                            h_scores = scores_map.get(cid, {})
                            
                            assessments.append({
                                "header_id": cid,
                                "date": datetime.fromisoformat(h["assessed_at"]).strftime('%Y-%m-%d') if h.get("assessed_at") else enc_map.get(h["encounter_id"], "-"),
                                "risk": h.get("overall_risk") or "รอสรุป",
                                "status": "สมบูรณ์" if sess.get("status") == "completed" else "กำลังดำเนินการ",
                                "mmse_score": h_scores.get("mmse"),
                                "tgds_score": h_scores.get("tgds"),
                                "source": "system"
                            })
            except Exception as system_err:
                print(f"Error fetching systemic assessments: {system_err}")

            # --- deduplicate and Sort ---
            # Group by Date + HN (simplified)
            unique_assessments = {}
            for a in assessments:
                # Try to avoid duplicates by date and key scores if available
                key = f"{a['date']}_{a['mmse_score']}_{a['tgds_score']}"
                if key not in unique_assessments:
                    unique_assessments[key] = a
                else:
                    # Prefer records with more data or from specific sources
                    existing = unique_assessments[key]
                    if (a['mmse_score'] is not None and existing['mmse_score'] is None):
                        unique_assessments[key] = a

            assessments = list(unique_assessments.values())
            assessments.sort(key=lambda x: x['date'])

            # Prepare chart data from combined results
            for a in assessments:
                chart_data["labels"].append(a["date"])
                chart_data["mmse"].append(a["mmse_score"] if a["mmse_score"] is not None else 0)
                chart_data["tgds"].append(a["tgds_score"] if a["tgds_score"] is not None else 0)
            
            # Reverse for display (Newest first)
            assessments.reverse()

        except Exception as e:
            print(f"Global assessments fetch error: {e}")
            # Fallback (Very basic)
            if not assessments:
                pass 
        
        return render_template("admin/patient_detail.html", 
                               patient=patient, 
                               primary_doctor=primary_doctor,
                               doctors=doctors, 
                               assessments=assessments, 
                               chart_data=chart_data,
                               active_page="patients")
        
    except Exception as e:
        print(f"Error fetching patient detail: {e}")
        flash(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}", "error")
        return redirect(url_for("admin.patients_list"))

@admin_bp.post("/patients/update/<int:id>")
def update_patient(id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    gender = request.form.get("gender", "").strip()
    birth_date = request.form.get("birth_date") or None
    address = request.form.get("address", "").strip()
    chronic_disease = request.form.get("chronic_disease", "").strip()
    emergency_contact_name = request.form.get("emergency_contact_name", "").strip()
    emergency_contact_phone = request.form.get("emergency_contact_phone", "").strip()
    primary_doctor_id = request.form.get("primary_doctor_id") or None
    
    if not full_name:
        flash("กรุณากรอกชื่อ-นามสกุล", "error")
        return redirect(url_for("admin.patient_detail", id=id))
        
    try:
        updated = False
        
        # 1. Update Supabase
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                data = {
                    "full_name": full_name,
                    "phone": phone,
                    "gender": gender,
                    "address": address,
                    "chronic_disease": chronic_disease,
                    "emergency_contact_name": emergency_contact_name,
                    "emergency_contact_phone": emergency_contact_phone,
                    "primary_doctor_id": primary_doctor_id,
                    "updated_at": datetime.now().isoformat()
                }
                if birth_date:
                    data["birth_date"] = birth_date
                else:
                    data["birth_date"] = None

                supabase.table("patients").update(data).eq("id", id).execute()
                updated = True
            except Exception as se:
                print(f"Supabase Update Error: {se}")
                flash(f"Supabase Error: {se}", "error")
        
        # 2. Update MySQL
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                # Try updating with all fields. Catch if columns missing.
                try:
                    cur.execute("""
                        UPDATE patients 
                        SET full_name=%s, gender=%s, birth_date=%s, phone=%s, address=%s,
                            chronic_disease=%s, emergency_contact_name=%s, emergency_contact_phone=%s
                        WHERE id=%s
                    """, (full_name, gender, birth_date, phone, address, chronic_disease, emergency_contact_name, emergency_contact_phone, id))
                except Exception as col_err:
                    # Fallback if chronic_disease missing
                    if "Unknown column" in str(col_err):
                        cur.execute("""
                            UPDATE patients 
                            SET full_name=%s, gender=%s, birth_date=%s, phone=%s, address=%s,
                                emergency_contact_name=%s, emergency_contact_phone=%s
                            WHERE id=%s
                        """, (full_name, gender, birth_date, phone, address, emergency_contact_name, emergency_contact_phone, id))
                    else:
                        raise col_err

                conn.commit()
                cur.close()
                conn.close()
                updated = True 
            except Exception as me:
                print(f"MySQL Update Error: {me}")
        
        if updated:
            flash("บันทึกข้อมูลเรียบร้อยแล้ว", "success")
        elif not updated and not get_flashed_messages():
            flash("ไม่สามารถบันทึกข้อมูลได้ (เชื่อมต่อฐานข้อมูลไม่ได้)", "error")
            
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.patient_detail", id=id))

@admin_bp.get("/doctors")
def doctors_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    q = (request.args.get("q") or "").strip()
    
    # Store doctors in a dict keyed by username for easy merging and deduplication
    merged_doctors = {}

    # 1. Fetch from Local MySQL (Primary for immediate visibility)
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            sql = "SELECT id, username, full_name, created_at, is_active FROM users WHERE role = 'doctor'"
            params = []
            if q:
                sql += " AND (full_name LIKE %s OR username LIKE %s)"
                params.extend([f"%{q}%", f"%{q}%"])
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, tuple(params))
            for r in cur.fetchall():
                next_duty = "ไม่มีข้อมูล"
                try:
                    cur.execute("SELECT start_datetime FROM doctor_duty_events WHERE doctor_id = %s AND start_datetime >= NOW() ORDER BY start_datetime ASC LIMIT 1", (r["id"],))
                    d_row = cur.fetchone()
                    if d_row: next_duty = d_row["start_datetime"].strftime('%d/%m/%Y %H:%M')
                except: pass

                uname_key = r['username'].lower()
                merged_doctors[uname_key] = {
                    "id": r["id"],
                    "username": r["username"],
                    "full_name": r["full_name"],
                    "is_active": int(r["is_active"]), 
                    "next_duty": next_duty,
                    "created_at": r["created_at"].strftime('%d/%m/%Y') if r["created_at"] else "-",
                    "source": "local"
                }
            cur.close(); conn.close()
    except Exception as me:
        print(f"MySQL Doctors Fetch Error: {me}")

    # 2. Fetch from Supabase and overwrite/merge (Cloud data takes precedence if synced)
    try:
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            query = supabase.table("users").select("id, username, full_name, created_at, is_active").eq("role", "doctor")
            if q: query = query.or_(f"full_name.ilike.%{q}%,username.ilike.%{q}%")
            resp = query.execute()
            
            for r in resp.data:
                uname_actual = r['username']
                uname_key = uname_actual.lower()
                if uname_key in merged_doctors:
                    current_local_status = merged_doctors[uname_key]['is_active']
                    merged_doctors[uname_key].update({
                        "id": r["id"],
                        "source": "cloud"
                    })
                    merged_doctors[uname_key]['is_active'] = current_local_status
                else:
                    merged_doctors[uname_key] = {
                        "id": r["id"],
                        "username": uname_actual,
                        "full_name": r["full_name"],
                        "is_active": int(r.get("is_active", True)),
                        "next_duty": "ไม่มีข้อมูล",
                        "created_at": datetime.fromisoformat(r["created_at"]).strftime('%d/%m/%Y') if r.get("created_at") else "-",
                        "source": "cloud"
                    }
    except Exception as se:
        print(f"Supabase Doctors Fetch Error: {se}")

    # Convert dict back to list and sort by name (Handle None in full_name)
    doctors = list(merged_doctors.values())
    doctors.sort(key=lambda x: x.get('full_name') or "")

    return render_template("admin/doctors.html", doctors=doctors, active_page="doctors", q=q)

    return render_template("admin/doctors.html", doctors=doctors, active_page="doctors", q=q)

@admin_bp.post("/doctors/add")
def add_doctor():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    # New Fields
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    bio = request.form.get("bio", "").strip()
    education = request.form.get("education", "").strip()
    
    if not full_name or not username or not password:
        flash("กรุณากรอกข้อมูลให้ครบถ้วน", "error")
        return redirect(url_for("admin.doctors_list"))
        
    password_hash = generate_password_hash(password)

    try:
        # 1. ALWAYS Save to Local MySQL First
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                flash("ชื่อผู้ใช้นี้มีอยู่ในระบบแล้ว (ในเครื่อง)", "error")
                cur.close(); conn.close()
                return redirect(url_for("admin.doctors_list"))
            
            # Try to insert with all fields
            try:
                cur.execute("""
                    INSERT INTO users (username, password_hash, full_name, role, is_active, created_at, 
                                      specialization, phone, email, bio, education)
                    VALUES (%s, %s, %s, 'doctor', 1, NOW(), %s, %s, %s, %s, %s)
                """, (username, password_hash, full_name, specialization, phone, email, bio, education))
            except Exception as e:
                print(f"Insert with extra fields failed: {e}")
                # Fallback to basic insert
                cur.execute("""
                    INSERT INTO users (username, password_hash, full_name, role, is_active, created_at)
                    VALUES (%s, %s, %s, 'doctor', 1, NOW())
                """, (username, password_hash, full_name))

            conn.commit()
            cur.close(); conn.close()
            print(f"✅ Doctor {username} saved to Local MySQL.")

        # 2. Try Supabase Sync
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                supabase.table("users").upsert({
                    "username": username,
                    "password_hash": password_hash,
                    "full_name": full_name,
                    "role": "doctor",
                    "is_active": True,
                    "created_at": datetime.now().isoformat(),
                    "specialization": specialization,
                    "phone": phone,
                    "email": email,
                    "bio": bio,
                    "education": education
                }, on_conflict="username").execute()
                flash("เพิ่มแพทย์และซิงค์ข้อมูลสำเร็จ", "success")
            except Exception as se:
                print(f"⚠️ Cloud Sync Failed for Doctor: {se}")
                flash("บันทึกแพทย์ในเครื่องสำเร็จแล้ว! (จะซิงค์ขึ้น Cloud ภายหลัง)", "warning")
        else:
            flash("เพิ่มแพทย์เรียบร้อยแล้ว (Local Only)", "success")

    except Exception as e:
        print(f"Add Doctor Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.doctors_list"))

@admin_bp.get("/doctors/<int:user_id>")
def doctor_detail(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    doctor = None
    duties = []
    patients = []
    primary_patients = []
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            
            # 1. Get doctor info from Supabase
            resp = supabase.table("users").select("*").eq("id", user_id).eq("role", "doctor").execute()
            if resp.data:
                doctor = resp.data[0]
                # Parse created_at string to datetime object for template compatibility
                if doctor.get("created_at") and isinstance(doctor["created_at"], str):
                    try:
                        # Handle ISO format from Supabase
                        dt_str = doctor["created_at"].replace("Z", "+00:00")
                        doctor["created_at"] = datetime.fromisoformat(dt_str)
                    except:
                        pass
            
            # 2. Get duties from Supabase (if table exists)
            try:
                # First try doctor_duty_events (the newer table)
                duty_resp = supabase.table("doctor_duty_events").select("*").eq("doctor_id", user_id).order("start_datetime", desc=True).limit(20).execute()
                for d in duty_resp.data:
                    duties.append({
                        "duty_date": d.get("start_datetime", "")[:10],
                        "shift_type": d.get("title", "Duty"),
                        "start_time": d.get("start_datetime", "")[11:16],
                        "end_time": d.get("end_datetime", "")[11:16],
                        "location": d.get("location"),
                        "note": d.get("description")
                    })
            except:
                # Fallback to doctor_duties if events table fails
                try:
                    duty_resp = supabase.table("doctor_duties").select("*").eq("doctor_id", user_id).order("duty_date", desc=True).limit(20).execute()
                    duties = duty_resp.data
                except:
                    pass

            # 3. Get treated patients from Supabase (From Doctor Notes)
            try:
                # ดึงข้อมูลจาก doctor_notes และ join ไปยัง encounters -> patients
                notes_resp = supabase.table("doctor_notes").select("*, encounters!inner(id, encounter_date, patients!inner(hn, full_name))").eq("doctor_id", user_id).order("created_at", desc=True).limit(50).execute()
                
                for n in notes_resp.data:
                    enc = n.get("encounters") or {}
                    p = enc.get("patients") or {}
                    patients.append({
                        "encounter_date": enc.get("encounter_date") or n.get("created_at")[:10],
                        "hn": p.get("hn") or "-",
                        "full_name": p.get("full_name") or "ไม่ระบุชื่อ",
                        "encounter_type": "การรักษา/วินิจฉัย",
                        "diagnosis": n.get("diagnosis") or "-"
                    })
                
                # หากยังไม่มีข้อมูลจาก doctor_notes ให้ลองดูจาก encounters ที่ assigned ไว้
                if not patients:
                    enc_resp = supabase.table("encounters").select("encounter_date, encounter_type, patients!inner(hn, full_name)").eq("assigned_doctor_id", user_id).order("encounter_date", desc=True).limit(30).execute()
                    for e in enc_resp.data:
                        p = e.get("patients")
                        patients.append({
                            "encounter_date": e.get("encounter_date")[:10] if e.get("encounter_date") else "-",
                            "hn": p.get("hn"),
                            "full_name": p.get("full_name"),
                            "encounter_type": e.get("encounter_type") or "ตรวจรักษาทั่วไป"
                        })
            except Exception as pe:
                print(f"Error fetching treated patients from Supabase: {pe}")

            # 4. Get primary patients from Supabase
            try:
                prim_resp = supabase.table("patients").select("id, hn, full_name, chronic_disease, phone").eq("primary_doctor_id", user_id).order("full_name").execute()
                primary_patients = prim_resp.data
            except:
                pass

        # If doctor not found in Supabase or Supabase not available, try MySQL
        if not doctor:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                # Fetch all columns to include new info fields
                cur.execute("SELECT * FROM users WHERE id = %s AND role = 'doctor'", (user_id,))
                doctor = cur.fetchone()
                
                if doctor:
                    # Only fetch other things from MySQL if we haven't already from Supabase
                    if not duties:
                        cur.execute("SELECT duty_date, shift_type, start_time, end_time, location, note FROM doctor_duties WHERE doctor_id = %s ORDER BY duty_date DESC LIMIT 20", (user_id,))
                        duties = cur.fetchall()
                    
                    if not patients:
                        cur.execute("""
                            SELECT e.encounter_date, p.hn, p.full_name, e.encounter_type
                            FROM encounters e
                            JOIN patients p ON e.patient_id = p.id
                            WHERE e.assigned_doctor_id = %s
                            ORDER BY e.encounter_date DESC
                            LIMIT 50
                        """, (user_id,))
                        patients = cur.fetchall()
                        
                    if not primary_patients:
                        try:
                            cur.execute("SELECT id, hn, full_name, chronic_disease, phone FROM patients WHERE primary_doctor_id = %s ORDER BY full_name", (user_id,))
                            primary_patients = cur.fetchall()
                        except:
                            pass
                
                cur.close(); conn.close()

    except Exception as e:
        print(f"Error in doctor_detail: {e}")
        # Final fallback attempt to MySQL if everything failed
        if not doctor:
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT id, username, full_name, role, is_active, created_at FROM users WHERE id = %s AND role = 'doctor'", (user_id,))
                    doctor = cur.fetchone()
                    cur.close(); conn.close()
            except:
                pass
    
    if not doctor:
        flash("ไม่พบข้อมูลแพทย์", "error")
        return redirect(url_for("admin.doctors_list"))
    
    return render_template("admin/doctor_detail.html", doctor=doctor, duties=duties, patients=patients, primary_patients=primary_patients, active_page="doctors")

@admin_bp.post("/doctors/update/<int:user_id>")
def update_doctor(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    # Identify the user by old_username to handle cases where Supabase ID != MySQL ID
    old_username = request.form.get("old_username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_active = request.form.get("is_active")
    
    # New Fields
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    bio = request.form.get("bio", "").strip()
    education = request.form.get("education", "").strip()
    
    if not full_name or not username:
        flash("กรุณากรอกชื่อ-นามสกุลและชื่อผู้ใช้", "error")
        return redirect(url_for("admin.doctor_detail", user_id=user_id))
        
    try:
        updated_mysql = False
        updated_supabase = False
        
        # 1. Update MySQL (Local) - Using old_username as the key
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                # Check if NEW username is taken (if it changed)
                if username.lower() != old_username.lower():
                    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                    if cur.fetchone():
                        flash("ชื่อผู้ใช้ใหม่นี้มีอยู่ในระบบแล้ว", "error")
                        cur.close(); conn.close()
                        return redirect(url_for("admin.doctor_detail", user_id=user_id))

                sql = """
                    UPDATE users 
                    SET full_name=%s, username=%s, is_active=%s, 
                        specialization=%s, phone=%s, email=%s, bio=%s, education=%s
                """
                params = [full_name, username, int(is_active), specialization, phone, email, bio, education]

                if password:
                    sql += ", password_hash=%s"
                    params.append(generate_password_hash(password))

                sql += " WHERE username=%s"
                params.append(old_username)

                cur.execute(sql, tuple(params))
                conn.commit()
                updated_mysql = True
                cur.close(); conn.close()
            except Exception as me:
                print(f"MySQL Update Error: {me}")

        # 2. Update Supabase (Cloud) - Using user_id (Supabase ID)
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                update_data = {
                    "full_name": full_name,
                    "username": username,
                    "is_active": bool(int(is_active)),
                    "specialization": specialization,
                    "phone": phone,
                    "email": email,
                    "bio": bio,
                    "education": education
                }
                if password:
                    update_data["password_hash"] = generate_password_hash(password)
                
                # Update by ID (Since we are in the detail page, this ID came from Supabase if source='cloud')
                res = supabase.table("users").update(update_data).eq("id", user_id).execute()
                if res.data:
                    updated_supabase = True
            except Exception as se:
                print(f"Supabase Update Doctor Error: {se}")
                flash(f"แจ้งเตือน: ไม่สามารถอัปเดตข้อมูลใน Supabase ได้ ({se})", "warning")
        
        if updated_mysql or updated_supabase:
            flash("บันทึกข้อมูลเรียบร้อยแล้ว", "success")
        else:
            flash("ไม่สามารถอัปเดตข้อมูลได้", "error")
            
    except Exception as e:
        print(f"Global Update Doctor Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.doctor_detail", user_id=user_id))

@admin_bp.get("/nurses")
def nurses_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    q = (request.args.get("q") or "").strip()
    
    # Store nurses in a dict keyed by username for easy merging and deduplication
    merged_nurses = {}

    # 1. Fetch from Local MySQL
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            sql = "SELECT id, username, full_name, created_at, is_active FROM users WHERE role = 'nurse'"
            params = []
            if q:
                sql += " AND (full_name LIKE %s OR username LIKE %s)"
                params.extend([f"%{q}%", f"%{q}%"])
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, tuple(params))
            for r in cur.fetchall():
                # บังคับ username เป็นตัวพิมพ์เล็กใน Key เพื่อการรวมข้อมูลที่ถูกต้อง
                uname_key = r['username'].lower()
                merged_nurses[uname_key] = {
                    "id": r["id"],
                    "username": r["username"], # เก็บชื่อจริงไว้แสดงผล
                    "full_name": r["full_name"],
                    "is_active": int(r["is_active"]),
                    "created_at": r["created_at"].strftime('%d/%m/%Y %H:%M') if r["created_at"] else "-",
                    "source": "local"
                }
            cur.close(); conn.close()
    except Exception as me:
        print(f"MySQL Nurses Fetch Error: {me}")

    # 2. Fetch from Supabase and merge
    try:
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            query = supabase.table("users").select("id, username, full_name, created_at, is_active").eq("role", "nurse")
            if q: query = query.or_(f"full_name.ilike.%{q}%,username.ilike.%{q}%")
            resp = query.execute()
            
            for r in resp.data:
                uname_actual = r['username']
                uname_key = uname_actual.lower()
                if uname_key in merged_nurses:
                    current_local_status = merged_nurses[uname_key]['is_active']
                    merged_nurses[uname_key].update({
                        "id": r["id"],
                        "source": "cloud"
                    })
                    merged_nurses[uname_key]['is_active'] = current_local_status
                else:
                    merged_nurses[uname_key] = {
                        "id": r["id"],
                        "username": uname_actual,
                        "full_name": r["full_name"],
                        "is_active": int(r.get("is_active", True)),
                        "created_at": datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).strftime('%d/%m/%Y %H:%M') if r.get("created_at") else "-",
                        "source": "cloud"
                    }
    except Exception as se:
        print(f"Supabase Nurses Fetch Error: {se}")

    # Convert to list and sort (Handle None in full_name)
    nurses = list(merged_nurses.values())
    nurses.sort(key=lambda x: x.get('full_name') or "")

    return render_template("admin/nurses.html", nurses=nurses, active_page="nurses", q=q)

@admin_bp.post("/nurses/add")
def add_nurse():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    # New Fields
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    bio = request.form.get("bio", "").strip()
    education = request.form.get("education", "").strip()
    
    if not full_name or not username or not password:
        flash("กรุณากรอกข้อมูลให้ครบถ้วน", "error")
        return redirect(url_for("admin.nurses_list"))
        
    password_hash = generate_password_hash(password)

    try:
        # 1. ALWAYS Save to Local MySQL First
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                flash("ชื่อผู้ใช้นี้มีอยู่ในระบบแล้ว (ในเครื่อง)", "error")
                cur.close(); conn.close()
                return redirect(url_for("admin.nurses_list"))
                
            cur.execute("""
                INSERT INTO users (username, password_hash, full_name, role, is_active, created_at,
                                  specialization, phone, email, bio, education)
                VALUES (%s, %s, %s, 'nurse', 1, NOW(), %s, %s, %s, %s, %s)
            """, (username, password_hash, full_name, specialization, phone, email, bio, education))
            conn.commit()
            cur.close(); conn.close()
            print(f"✅ Nurse {username} saved to Local MySQL.")

        # 2. Try Supabase Sync
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                supabase.table("users").upsert({
                    "username": username,
                    "password_hash": password_hash,
                    "full_name": full_name,
                    "role": "nurse",
                    "is_active": True,
                    "created_at": datetime.now().isoformat(),
                    "specialization": specialization,
                    "phone": phone,
                    "email": email,
                    "bio": bio,
                    "education": education
                }, on_conflict="username").execute()
                flash("เพิ่มพยาบาลและซิงค์ข้อมูลสำเร็จ", "success")
            except Exception as se:
                print(f"⚠️ Cloud Sync Failed for Nurse: {se}")
                flash("บันทึกพยาบาลในเครื่องสำเร็จแล้ว! (จะซิงค์ขึ้น Cloud ภายหลัง)", "warning")
        else:
            flash("เพิ่มพยาบาลเรียบร้อยแล้ว (Local Only)", "success")

    except Exception as e:
        print(f"Add Nurse Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.nurses_list"))

@admin_bp.get("/nurses/<int:user_id>")
def nurse_detail(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    nurse = None
    assessments = []
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            
            # 1. Get nurse info
            resp = supabase.table("users").select("*").eq("id", user_id).eq("role", "nurse").execute()
            if resp.data:
                nurse = resp.data[0]
                if isinstance(nurse.get("created_at"), str):
                    try:
                        nurse["created_at"] = datetime.fromisoformat(nurse["created_at"].replace("Z", "+00:00"))
                    except:
                        pass
            
            # 2. Get recent assessments by this nurse from cga_records
            try:
                # Use nurse full_name or ID to match assessments if cga_records stores assessor info
                # If cga_records doesn't have assessed_by, we might need to filter by nurse name or other logic.
                # Assuming we filter by some identifier or just show general recent ones for this context if specific link is missing.
                # Here we attempt to fetch based on the nurse's full name if that's how it's linked in cga_records
                
                ass_resp = supabase.table("cga_records").select("*").order("assessed_date", desc=True).limit(20).execute()
                
                for r in ass_resp.data:
                    dt_val = None
                    if r.get("assessed_date"):
                        try:
                            # Handle simple YYYY-MM-DD or ISO
                            d_str = r["assessed_date"]
                            if "T" in d_str:
                                dt_val = datetime.fromisoformat(d_str.replace("Z", "+00:00"))
                            else:
                                dt_val = datetime.strptime(d_str, "%Y-%m-%d")
                        except:
                            pass

                    assessments.append({
                        "id": r["id"],
                        "assessed_at": dt_val,
                        "hn": r.get("hn"),
                        "patient_name": r.get("full_name"), # ดึงชื่อจาก cga_records เสมอ
                        "overall_risk": r.get("mmse_result")
                    })
            except Exception as e:
                print(f"Error fetching nurse assessments from cga_records: {e}")

        # Fallback to MySQL
        if not nurse:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                # Fetch all columns to include new info fields
                cur.execute("SELECT * FROM users WHERE id = %s AND role = 'nurse'", (user_id,))
                nurse = cur.fetchone()
                
                if nurse and not assessments:
                    cur.execute("""
                        SELECT ch.id, ch.assessed_at, p.hn, p.full_name AS patient_name, ch.overall_risk
                        FROM cga_headers ch
                        JOIN encounters e ON ch.encounter_id = e.id
                        JOIN patients p ON e.patient_id = p.id
                        WHERE ch.assessed_by = %s
                        ORDER BY ch.assessed_at DESC
                        LIMIT 20
                    """, (user_id,))
                    assessments = cur.fetchall()
                cur.close(); conn.close()

    except Exception as e:
        print(f"Error in nurse_detail: {e}")
        if not nurse:
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT * FROM users WHERE id = %s AND role = 'nurse'", (user_id,))
                    nurse = cur.fetchone()
                    cur.close(); conn.close()
            except:
                pass

    if not nurse:
        flash("ไม่พบข้อมูลพยาบาล", "error")
        return redirect(url_for("admin.nurses_list"))
    
    return render_template("admin/nurse_detail.html", nurse=nurse, assessments=assessments, active_page="nurses")

@admin_bp.post("/nurses/update/<int:user_id>")
def update_nurse(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    old_username = request.form.get("old_username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_active = request.form.get("is_active")
    
    # New Fields
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    bio = request.form.get("bio", "").strip()
    education = request.form.get("education", "").strip()
    
    if not full_name or not username:
        flash("กรุณากรอกชื่อ-นามสกุลและชื่อผู้ใช้", "error")
        return redirect(url_for("admin.nurse_detail", user_id=user_id))
        
    try:
        updated_mysql = False
        updated_supabase = False
        
        # 1. MySQL (Local)
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                if username.lower() != old_username.lower():
                    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                    if cur.fetchone():
                        flash("ชื่อผู้ใช้ใหม่นี้มีอยู่ในระบบแล้ว", "error")
                        cur.close(); conn.close()
                        return redirect(url_for("admin.nurse_detail", user_id=user_id))

                sql = """
                    UPDATE users 
                    SET full_name=%s, username=%s, is_active=%s,
                        specialization=%s, phone=%s, email=%s, bio=%s, education=%s
                """
                params = [full_name, username, int(is_active), specialization, phone, email, bio, education]

                if password:
                    sql += ", password_hash=%s"
                    params.append(generate_password_hash(password))

                sql += " WHERE username=%s"
                params.append(old_username)

                cur.execute(sql, tuple(params))
                conn.commit()
                updated_mysql = True
                cur.close(); conn.close()
            except Exception as me:
                print(f"MySQL Nurse Update Error: {me}")

        # 2. Supabase
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                update_data = {
                    "full_name": full_name,
                    "username": username,
                    "is_active": bool(int(is_active)),
                    "specialization": specialization,
                    "phone": phone,
                    "email": email,
                    "bio": bio,
                    "education": education
                }
                if password:
                    update_data["password_hash"] = generate_password_hash(password)
                
                res = supabase.table("users").update(update_data).eq("id", user_id).execute()
                if res.data:
                    updated_supabase = True
            except Exception as se:
                print(f"Supabase Update Nurse Error: {se}")
                flash(f"แจ้งเตือน: ไม่สามารถอัปเดตข้อมูลใน Supabase ได้ ({se})", "warning")
        
        if updated_mysql or updated_supabase:
            flash("บันทึกข้อมูลเรียบร้อยแล้ว", "success")
        else:
            flash("ไม่สามารถอัปเดตข้อมูลได้", "error")
            
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.nurse_detail", user_id=user_id))

@admin_bp.post("/doctors/delete/<int:user_id>")
def delete_doctor(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    try:
        # 1. Delete from MySQL
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id = %s AND role = 'doctor'", (user_id,))
            conn.commit()
            cur.close(); conn.close()

        # 2. Delete from Supabase
        # Note: If the ID is different between systems, this might fail or delete the wrong user.
        # Ideally we should use a unique identifier like 'username' if IDs aren't synced.
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                supabase.table("users").delete().eq("id", user_id).eq("role", "doctor").execute()
            except Exception as se:
                print(f"Supabase Delete Doctor Error: {se}")
                flash(f"แจ้งเตือน: ไม่สามารถลบจาก Supabase ได้ ({se})", "warning")

        flash("ลบข้อมูลแพทย์เรียบร้อยแล้ว", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.doctors_list"))

@admin_bp.post("/nurses/delete/<int:user_id>")
def delete_nurse(user_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    try:
        # 1. Delete from MySQL
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id = %s AND role = 'nurse'", (user_id,))
            conn.commit()
            cur.close(); conn.close()

        # 2. Delete from Supabase
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                supabase.table("users").delete().eq("id", user_id).eq("role", "nurse").execute()
            except Exception as se:
                print(f"Supabase Delete Nurse Error: {se}")
                flash(f"แจ้งเตือน: ไม่สามารถลบจาก Supabase ได้ ({se})", "warning")

        flash("ลบข้อมูลพยาบาลเรียบร้อยแล้ว", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("admin.nurses_list"))

@admin_bp.get("/users/toggle-status/<username>")
def toggle_user_status(username: str):
    if not _require_admin(): return {"error": "Unauthorized"}, 401
    
    role = request.args.get("role", "nurse")
    target_url = url_for(f"admin.{role}s_list")
    
    conn = None
    new_status_bool = False
    updated_local = False
    
    try:
        # 1. จัดการ MySQL (Local)
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT is_active FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            
            if user:
                # บังคับสลับค่า 1 เป็น 0 และ 0 เป็น 1
                new_status_int = 0 if int(user["is_active"]) == 1 else 1
                new_status_bool = True if new_status_int == 1 else False
                cur.execute("UPDATE users SET is_active = %s WHERE username = %s", (new_status_int, username))
                conn.commit()
                updated_local = True
            cur.close()

        # 2. จัดการ Supabase (Cloud)
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        
        if supabase_url and supabase_key:
            try:
                supabase: Client = create_client(supabase_url, supabase_key)
                
                # ถ้าในเครื่องไม่เจอ ให้ไปเช็คสถานะจาก Cloud แทน
                if not updated_local:
                    res = supabase.table("users").select("is_active").eq("username", username).execute()
                    if res.data:
                        current_cloud_status = res.data[0].get("is_active", True)
                        new_status_bool = not current_cloud_status
                
                # สั่งอัปเดต Cloud
                supabase.table("users").update({"is_active": new_status_bool}).eq("username", username).execute()
            except Exception as se:
                print(f"Supabase Sync Toggle Error: {se}")

        flash(f"เปลี่ยนสถานะของ {username} เป็น {'ปกติ' if new_status_bool else 'ระงับ'} เรียบร้อยแล้ว", "success")
    except Exception as e:
        print(f"Toggle Status Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
    finally:
        if conn: conn.close()
        
    return redirect(target_url)

@admin_bp.get("/appointments")
def appointments_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    appts = []
    
    try:
        supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
        supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
        
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            query = supabase.table("appointments").select("appt_datetime, appt_type, status, note, patients(hn, full_name)")
            
            if start_date:
                query = query.gte("appt_datetime", start_date + "T00:00:00")
            if end_date:
                query = query.lte("appt_datetime", end_date + "T23:59:59")
                
            resp = query.order("appt_datetime", desc=True).limit(200).execute()
            
            for r in resp.data:
                p = r.get("patients") or {}
                appts.append({
                    "appt_datetime": datetime.fromisoformat(r["appt_datetime"]).strftime('%d/%m/%Y %H:%M') if r.get("appt_datetime") else "-",
                    "appt_type": r.get("appt_type"),
                    "status": r.get("status") or "scheduled",
                    "note": r.get("note"),
                    "hn": p.get("hn", "-"),
                    "full_name": p.get("full_name", "-")
                })
        else:
            # Fallback to MySQL
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                sql = "SELECT a.appt_datetime, p.hn, p.full_name, a.appt_type, a.status, a.note FROM appointments a JOIN patients p ON a.patient_id = p.id"
                params = []
                if start_date or end_date:
                    sql += " WHERE"
                    if start_date:
                        sql += " a.appt_datetime >= %s"
                        params.append(start_date + " 00:00:00")
                    if end_date:
                        if start_date: sql += " AND"
                        sql += " a.appt_datetime <= %s"
                        params.append(end_date + " 23:59:59")
                
                sql += " ORDER BY a.appt_datetime DESC LIMIT 200"
                cur.execute(sql, tuple(params))
                appts = cur.fetchall()
                cur.close(); conn.close()
                
    except Exception as e:
        print(f"Error fetching appointments: {e}")

    return render_template("admin/appointments.html", appointments=appts, active_page="appointments", start_date=start_date, end_date=end_date)

@admin_bp.get("/assessments")
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

@admin_bp.get("/assessments/<int:header_id>")
def assessment_detail(header_id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    header = None
    scores = []
    grouped_answers = {} # Initialize to prevent UndefinedError in template
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            
            # 1. Fetch from cga_records
            resp = supabase.table("cga_records").select("*").eq("id", header_id).execute()
            if resp.data:
                raw_header = resp.data[0]
                
                # 2. Fetch the REAL patient data to ensure HN is correct (Real-time sync)
                patient_id = raw_header.get("patient_id")
                patient_data = {}
                if patient_id:
                    p_resp = supabase.table("patients").select("*").eq("id", patient_id).execute()
                    if p_resp.data:
                        patient_data = p_resp.data[0]
                
                # Parse dates to objects for template strftime
                assessed_val = raw_header.get("assessed_date") or raw_header.get("created_at")
                if isinstance(assessed_val, str):
                    try:
                        # Handle ISO format from Supabase
                        if "T" in assessed_val:
                            assessed_val = datetime.fromisoformat(assessed_val.replace("Z", "+00:00"))
                        else:
                            # Handle simple YYYY-MM-DD
                            assessed_val = datetime.strptime(assessed_val, "%Y-%m-%d")
                    except:
                        pass

                bdate_val = patient_data.get("birth_date")
                if isinstance(bdate_val, str):
                    try:
                        bdate_val = datetime.strptime(bdate_val, "%Y-%m-%d")
                    except:
                        pass

                # Calculate Real Overall Risk for the Summary Card
                risks_found = []
                max_color = 'green'
                
                mmse_res = (raw_header.get("mmse_result") or "").lower()
                tgds_res = (raw_header.get("tgds_result") or "").lower()
                suicide_res = (raw_header.get("suicide_risk") or "").lower()

                if "high" in mmse_res or "สูง" in mmse_res or "ผิดปกติ" in mmse_res:
                    risks_found.append("สมองเสื่อม")
                    max_color = 'red'
                elif "medium" in mmse_res or "กลาง" in mmse_res or "สงสัย" in mmse_res:
                    risks_found.append("สมองเสื่อม")
                    if max_color != 'red': max_color = 'orange'

                if "high" in tgds_res or "สูง" in tgds_res or "ซึมเศร้า" in tgds_res:
                    risks_found.append("ซึมเศร้า")
                    max_color = 'red'
                elif "medium" in tgds_res or "กลาง" in tgds_res or "สงสัย" in tgds_res:
                    risks_found.append("ซึมเศร้า")
                    if max_color != 'red': max_color = 'orange'

                if "high" in suicide_res or "สูง" in suicide_res or "มีแนวโน้ม" in suicide_res:
                    risks_found.append("ฆ่าตัวตาย")
                    max_color = 'red'

                if not risks_found:
                    overall_text = "ปกติ (ไม่พบความเสี่ยง)"
                else:
                    prefix = "เสี่ยงสูง" if max_color == 'red' else "เสี่ยง"
                    overall_text = f"{prefix} ({', '.join(risks_found)})"
                
                # Map to header object for template
                header = {
                    "id": raw_header.get("id"),
                    "hn": patient_data.get("hn") or raw_header.get("hn"), # Priority to Patient Table
                    "full_name": patient_data.get("full_name") or raw_header.get("full_name"),
                    "gender": patient_data.get("gender"),
                    "birth_date": bdate_val,
                    "assessed_at": assessed_val,
                    "mmse_score": raw_header.get("mmse_score"),
                    "mmse_result": raw_header.get("mmse_result"),
                    "tgds_score": raw_header.get("tgds_score"),
                    "tgds_result": raw_header.get("tgds_result"),
                    "suicide_risk": raw_header.get("suicide_risk"),
                    "overall_risk": overall_text,
                    "risk_color": max_color,
                    "age": raw_header.get("age"),
                    "education": raw_header.get("education"),
                    "caregiver_name": raw_header.get("caregiver_name"),
                    "caregiver_relation": raw_header.get("caregiver_relation"),
                    "note": raw_header.get("note")
                }
                
                # Map all columns to grouped_answers with specific English labels
                grouped_answers = {
                    "General Information": [
                        {"question_label": "age", "value_text": header["age"]},
                        {"question_label": "education", "value_text": header["education"]},
                        {"question_label": "caregiver", "value_text": header["caregiver_name"]},
                        {"question_label": "relation", "value_text": header["caregiver_relation"]},
                        {"question_label": "emergency phone", "value_text": raw_header.get("emergency_phone")},
                    ],
                    "Lifestyle & Habits": [
                        {"question_label": "smoke", "value_text": raw_header.get("smoke")},
                        {"question_label": "alcohol", "value_text": raw_header.get("alcohol")},
                    ],
                    "Physical Assessment": [
                        {"question_label": "vision left", "value_text": raw_header.get("vision_left")},
                        {"question_label": "vision_right", "value_text": raw_header.get("vision_right")},
                        {"question_label": "hearing_left", "value_text": raw_header.get("hearing_left")},
                        {"question_label": "hearing_right", "value_text": raw_header.get("hearing_right")},
                        {"question_label": "incontinence", "value_text": raw_header.get("incontinence")},
                        {"question_label": "sleep problem", "value_text": raw_header.get("sleep_problem")},
                    ],
                    "Screening Results": [
                        {"question_label": "mmse score", "value_text": header["mmse_score"]},
                        {"question_label": "mmse result", "value_text": header["mmse_result"]},
                        {"question_label": "tgds score", "value_text": header["tgds_score"]},
                        {"question_label": "tgds_result", "value_text": header["tgds_result"]},
                        {"question_label": "suicide risk", "value_text": header["suicide_risk"]},
                    ]
                }
                
                # Construct scores list for display
                if header["mmse_score"] is not None:
                    scores.append({"instrument": "MMSE", "total_score": header["mmse_score"], "risk_level": header["mmse_result"]})
                if header["tgds_score"] is not None:
                    scores.append({"instrument": "TGDS", "total_score": header["tgds_score"], "risk_level": header["tgds_result"]})
                if header["suicide_risk"]:
                    scores.append({"instrument": "Suicide Risk", "total_score": "-", "risk_level": header["suicide_risk"]})

        # Fallback to MySQL if not found in Supabase
        if not header:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                # Try stg_cga_csv which has similar columns to cga_records
                try:
                    cur.execute("SELECT * FROM stg_cga_csv WHERE id = %s OR hn = (SELECT hn FROM cga_records WHERE id = %s)", (header_id, header_id))
                    stg_data = cur.fetchone()
                    if stg_data:
                        header = {
                            "id": stg_data["id"],
                            "hn": stg_data["hn"],
                            "full_name": f"{stg_data.get('first_name','')} {stg_data.get('last_name','')}",
                            "gender": stg_data.get("sex"),
                            "birth_date": stg_data.get("dob_text"),
                            "assessed_at": stg_data.get("assessed_date_text"),
                            "mmse_score": stg_data.get("mmse_score"),
                            "mmse_result": stg_data.get("mmse_result"),
                            "tgds_score": stg_data.get("tgds_score"),
                            "tgds_result": stg_data.get("tgds_result"),
                            "suicide_risk": stg_data.get("suicide_risk_level"),
                            "overall_risk": stg_data.get("mmse_result"),
                            "age": stg_data.get("age"),
                            "education": stg_data.get("education"),
                            "caregiver_name": stg_data.get("caregiver_name"),
                            "caregiver_relation": "-",
                            "emergency_phone": stg_data.get("phone")
                        }
                        # Populate grouped_answers for MySQL data too
                        grouped_answers = {
                            "General Information": [
                                {"question_label": "age", "value_text": header["age"]},
                                {"question_label": "education", "value_text": header["education"]},
                                {"question_label": "caregiver", "value_text": header["caregiver_name"]},
                                {"question_label": "relation", "value_text": header["caregiver_relation"]},
                                {"question_label": "emergency phone", "value_text": header["emergency_phone"]},
                            ],
                            "Lifestyle & Habits": [
                                {"question_label": "smoke", "value_text": stg_data.get("smoke", "-")},
                                {"question_label": "alcohol", "value_text": stg_data.get("alcohol", "-")},
                            ],
                            "Physical Assessment": [
                                {"question_label": "vision left", "value_text": stg_data.get("vision_left_snellen", "-")},
                                {"question_label": "vision_right", "value_text": stg_data.get("vision_right_snellen", "-")},
                                {"question_label": "hearing_left", "value_text": stg_data.get("hearing_left_result", "-")},
                                {"question_label": "hearing_right", "value_text": stg_data.get("hearing_right_result", "-")},
                                {"question_label": "incontinence", "value_text": stg_data.get("incontinence", "-")},
                                {"question_label": "sleep problem", "value_text": stg_data.get("sleep_problem", "-")},
                            ],
                            "Screening Results": [
                                {"question_label": "mmse score", "value_text": header["mmse_score"]},
                                {"question_label": "mmse result", "value_text": header["mmse_result"]},
                                {"question_label": "tgds score", "value_text": header["tgds_score"]},
                                {"question_label": "tgds_result", "value_text": header["tgds_result"]},
                                {"question_label": "suicide risk", "value_text": header["suicide_risk"]},
                            ]
                        }
                except:
                    pass
                
                if not header:
                    cur.execute("""
                        SELECT ch.*, p.hn, p.full_name, p.gender, p.birth_date
                        FROM cga_headers ch
                        JOIN encounters e ON ch.encounter_id = e.id
                        JOIN patients p ON e.patient_id = p.id
                        WHERE ch.id = %s
                    """, (header_id,))
                    header = cur.fetchone()
                
                if header and not scores:
                    cur.execute("SELECT instrument, total_score, risk_level, note FROM assessment_scores WHERE cga_id = %s", (header_id,))
                    scores = cur.fetchall()
                cur.close(); conn.close()

    except Exception as e:
        print(f"Error in assessment_detail: {e}")

    if not header:
        flash("ไม่พบข้อมูลการประเมิน", "error")
        return redirect(url_for("admin.assessments_list"))

    return render_template("admin/assessment_detail.html", header=header, scores=scores, grouped_answers=grouped_answers)
    cur.execute("SELECT total_score, risk_level FROM assessment_tgds WHERE cga_id = %s", (header_id,))
    tgds_data = cur.fetchone()
    if tgds_data:
        if not any(s['instrument'] == 'tgds' for s in scores):
            scores.append({'instrument': 'tgds', 'total_score': tgds_data['total_score'], 'risk_level': tgds_data['risk_level'], 'note': ''})

    # 3. Get answers from multiple possible tables
    answers = []
    
    # Try the centralized answers table
    if sid:
        cur.execute("SELECT instrument, question_no, answer_text, score FROM assessment_answers WHERE cga_id = %s OR session_id = %s ORDER BY instrument, question_no", (header_id, sid))
    else:
        cur.execute("SELECT instrument, question_no, answer_text, score FROM assessment_answers WHERE cga_id = %s ORDER BY instrument, question_no", (header_id,))
    answers.extend(cur.fetchall())
    
    # Try MMSE specific items table
    cur.execute("""
        SELECT 'mmse' as instrument, question_no, answer_text, score 
        FROM assessment_mmse_items i
        JOIN assessment_mmse m ON i.mmse_id = m.id
        WHERE m.cga_id = %s
        ORDER BY question_no
    """, (header_id,))
    answers.extend(cur.fetchall())

    # Try TGDS specific items table
    cur.execute("""
        SELECT 'tgds' as instrument, question_no, CAST(answer AS CHAR) as answer_text, score 
        FROM assessment_tgds_items i
        JOIN assessment_tgds t ON i.tgds_id = t.id
        WHERE t.cga_id = %s
        ORDER BY question_no
    """, (header_id,))
    answers.extend(cur.fetchall())

    cur.close(); conn.close()
    
    # Group answers by instrument (and deduplicate if necessary)
    grouped_answers = {}
    seen_answers = set()
    for ans in answers:
        key = (ans['instrument'], ans['question_no'])
        if key not in seen_answers:
            seen_answers.add(key)
            instr = ans['instrument']
            if instr not in grouped_answers:
                grouped_answers[instr] = []
            grouped_answers[instr].append(ans)
        
    return render_template("admin/assessment_detail.html", 
                           header=header, 
                           scores=scores, 
                           grouped_answers=grouped_answers,
                           active_page="assessments")

@admin_bp.get("/permissions")
def permissions_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    q = (request.args.get("q") or "").strip()
    role_filter = (request.args.get("role") or "").strip()
    
    # Initialize Supabase client
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    supabase_client = None
    if supabase_url and supabase_key:
        try:
            supabase_client = create_client(supabase_url, supabase_key)
        except Exception as e:
            print(f"Supabase Init Error in permissions_list: {e}")

    stats = {
        "total_users": 0,
        "active_users": 0,
        "doctors": 0,
        "nurses": 0
    }
    users_list = []
    
    # 1. Try fetching from Supabase
    if supabase_client:
        try:
            # Total Users (filtered by roles)
            res_total = supabase_client.table("users").select("id", count="exact").in_("role", ["admin", "doctor", "nurse"]).execute()
            stats["total_users"] = res_total.count or 0
            
            # Doctors
            res_doctors = supabase_client.table("users").select("id", count="exact").eq("role", "doctor").execute()
            stats["doctors"] = res_doctors.count or 0
            
            # Nurses
            res_nurses = supabase_client.table("users").select("id", count="exact").eq("role", "nurse").execute()
            stats["nurses"] = res_nurses.count or 0
            
            # Fetch Users List with filters
            query = supabase_client.table("users").select("id, username, full_name, role, is_active, created_at").in_("role", ["admin", "doctor", "nurse"])
            
            if role_filter:
                query = query.eq("role", role_filter)
            
            if q:
                query = query.or_(f"full_name.ilike.%{q}%,username.ilike.%{q}%")
                
            query = query.order("role").order("full_name")
            res_users = query.execute()
            users_list = res_users.data or []
            
        except Exception as e:
            print(f"Error fetching users from Supabase: {e}")
            supabase_client = None # Mark as failed to allow fallback

    # 2. Local DB for active_users and fallback if Supabase failed
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(dictionary=True)
            
            # Active users (last 24h) from local audit_logs
            cur.execute("""
                SELECT COUNT(DISTINCT actor_user_id) as c 
                FROM audit_logs 
                WHERE action = 'login' 
                  AND created_at >= NOW() - INTERVAL 1 DAY
            """)
            row = cur.fetchone()
            stats["active_users"] = row["c"] if row else 0

            # Fallback if Supabase is not available
            if not supabase_client:
                cur.execute("SELECT COUNT(*) as c FROM users WHERE role IN ('admin', 'doctor', 'nurse')")
                stats["total_users"] = cur.fetchone()["c"]
                
                cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'doctor'")
                stats["doctors"] = cur.fetchone()["c"]
                
                cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'nurse'")
                stats["nurses"] = cur.fetchone()["c"]

                sql = "SELECT id, username, full_name, role, is_active, created_at FROM users WHERE role IN ('admin', 'doctor', 'nurse')"
                params = []
                if role_filter:
                    sql += " AND role = %s"
                    params.append(role_filter)
                if q:
                    sql += " AND (full_name LIKE %s OR username LIKE %s)"
                    params.extend([f"%{q}%", f"%{q}%"])
                sql += " ORDER BY role, full_name"
                cur.execute(sql, tuple(params))
                users_list = cur.fetchall()
            
            cur.close()
        except Exception as e:
            print(f"Error fetching from Local DB in permissions_list: {e}")
        finally:
            conn.close()

    return render_template("admin/permissions.html", active_page="permissions", stats=stats, users=users_list, q=q, role_filter=role_filter)

@admin_bp.post("/sync-offline-data")
def sync_offline_data():
    if not _require_admin(): return {"error": "Unauthorized"}, 401
    
    sync_count = 0
    errors = []
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    if not supabase_url or not supabase_key:
        return {"error": "Cloud settings missing"}, 400

    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        conn = get_db_connection()
        if not conn: return {"error": "Local DB error"}, 500
        cur = conn.cursor(dictionary=True)

        # 1. Sync Patients
        cur.execute("SELECT * FROM patients") # In a real app, we'd filter by an is_synced flag
        local_patients = cur.fetchall()
        
        for p in local_patients:
            try:
                # Upsert to Supabase
                p_data = {
                    "hn": p["hn"],
                    "full_name": p["full_name"],
                    "gender": p["gender"],
                    "birth_date": str(p["birth_date"]) if p["birth_date"] else None,
                    "phone": p["phone"],
                    "address": p["address"],
                    "created_at": p["created_at"].isoformat() if p["created_at"] else None
                }
                supabase.table("patients").upsert(p_data, on_conflict="hn").execute()
                sync_count += 1
            except Exception as se:
                errors.append(f"Patient {p['hn']}: {str(se)}")

        cur.close(); conn.close()
        return {"success": True, "synced": sync_count, "errors": errors}

    except Exception as e:
        return {"error": str(e)}, 500

import io
import csv
from flask import Response

@admin_bp.get("/executive-report/export")
@admin_bp.get("/executive-report/export")
def export_executive_csv():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    # Logic to fetch data (similar to executive_report)
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    output = io.StringIO()
    # Add BOM for Excel UTF-8 compatibility
    output.write('\ufeff')
    writer = csv.writer(output)
    
    writer.writerow(['หัวข้อรายงาน', 'ค่าสถิติ', 'หน่วย'])
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            res_p = supabase.table("patients").select("id", count="exact").execute()
            res_a = supabase.table("cga_records").select("*").execute()
            
            total_p = res_p.count or 0
            records = res_a.data or []
            total_a = len(records)
            
            high_risk = 0
            for r in records:
                risk = (r.get("mmse_result") or "").lower()
                if "high" in risk or "สูง" in risk: high_risk += 1
            
            completion = round((total_a / total_p * 100), 1) if total_p > 0 else 0
            
            writer.writerow(['จำนวนผู้ป่วยเป้าหมายสะสม', total_p, 'ราย'])
            writer.writerow(['จำนวนการประเมินทั้งหมด', total_a, 'ครั้ง'])
            writer.writerow(['ความครอบคลุมการคัดกรอง', completion, '%'])
            writer.writerow(['จำนวนกลุ่มเสี่ยงสูง', high_risk, 'ราย'])
            
    except Exception as e:
        writer.writerow(['เกิดข้อผิดพลาด', str(e), ''])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=Executive_Summary_{date.today()}.csv"}
    )
@admin_bp.get("/executive-report")
def executive_report():
    if not _require_admin(): return redirect(url_for("auth.login"))
    
    stats = {
        "total_patients": 0,
        "total_assessments": 0,
        "high_risk_count": 0,
        "normal_count": 0,
        "completion_rate": 0
    }
    
    risk_distribution = {"high": 0, "medium": 0, "normal": 0}
    age_groups = {"60-70": 0, "71-80": 0, "81+": 0}
    
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    
    try:
        if supabase_url and supabase_key:
            supabase: Client = create_client(supabase_url, supabase_key)
            
            # 1. Overall Stats
            res_p = supabase.table("patients").select("id", count="exact").execute()
            stats["total_patients"] = res_p.count or 0
            
            res_a = supabase.table("cga_records").select("*").execute()
            records = res_a.data or []
            stats["total_assessments"] = len(records)
            
            # 2. Analyze Records for Executive View
            for r in records:
                risk = (r.get("mmse_result") or "").lower()
                if "high" in risk or "สูง" in risk: risk_distribution["high"] += 1
                elif "medium" in risk or "กลาง" in risk or "เสี่ยง" in risk: risk_distribution["medium"] += 1
                else: risk_distribution["normal"] += 1
                
                # Age grouping
                age = r.get("age") or 0
                if 60 <= age <= 70: age_groups["60-70"] += 1
                elif 71 <= age <= 80: age_groups["71-80"] += 1
                elif age > 80: age_groups["81+"] += 1

            stats["high_risk_count"] = risk_distribution["high"]
            stats["normal_count"] = risk_distribution["normal"]
            
            if stats["total_patients"] > 0:
                stats["completion_rate"] = round((stats["total_assessments"] / stats["total_patients"]) * 100, 1)

    except Exception as e:
        print(f"Executive Report Error: {e}")

    return render_template("admin/executive_report.html", 
                           stats=stats, 
                           risk_dist=risk_distribution,
                           age_groups=age_groups,
                           active_page="executive_report")

@admin_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
