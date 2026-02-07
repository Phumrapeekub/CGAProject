from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
from db.db import get_db_connection
from datetime import datetime, date, timedelta

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")

def _guard_doctor() -> bool:
    return bool(session.get("logged_in")) and session.get("role") == "doctor"

def _thai_months_full():
    return [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    ]

def format_thai_short_with_year(d_str: str) -> str:
    if not d_str: return "-"
    try:
        d = datetime.fromisoformat(d_str.split('T')[0])
        m = _thai_months_full()[d.month - 1]
        y = d.year + 543
        return f"{d.day} {m[:3]} {y}"
    except:
        return d_str

@doctor_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        supabase = get_db_connection()
        if not supabase:
            flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
            return redirect(url_for("doctor.login"))

        try:
            resp = supabase.table("users").select("*").eq("username", username).limit(1).execute()
            user = resp.data[0] if resp.data else None

            if user and check_password_hash(user["password_hash"], password) and user.get("role") == "doctor":
                session.clear()
                session["logged_in"] = True
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = "doctor"
                return redirect(url_for("doctor.dashboard"))
            
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
        except Exception as e:
            flash(f"Login Error: {e}", "error")

    return render_template("auth/login.html", post_url=url_for("doctor.login"), role_label="แพทย์")

@doctor_bp.get("/dashboard")
def dashboard():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    supabase = get_db_connection()
    try:
        # KPI Stats using SDK
        total_patients = supabase.table("patients").select("*", count="exact").execute().count
        
        today = date.today().isoformat()
        today_encounters = supabase.table("encounters").select("*", count="exact").eq("encounter_date", today).execute().count
        
        # Get latest assessments
        latest_resp = supabase.table("encounters").select("*, patients(hn, full_name)").order("created_at", desc=True).limit(5).execute()
        latest_assessments = []
        for r in latest_resp.data:
            p = r.get("patients") or {}
            latest_assessments.append({
                "patient_id": r["patient_id"],
                "hn": p.get("hn", "-"),
                "name": p.get("full_name", "-"),
                "date_th": format_thai_short_with_year(r["encounter_date"])
            })

        kpis = {
            "total_patients": total_patients,
            "today_patients": today_encounters,
            "high_risk": 0, # Placeholder for now
            "avg_cga_score": 0
        }

        return render_template(
            "doctor/medical_dashboard.html",
            kpis=kpis,
            latest_assessments=latest_assessments,
            today_appointments=[],
            risk_labels=["ปกติ", "เสี่ยง", "ผิดปกติ"],
            risk_data=[0, 0, 0],
            age_labels=["60-64", "65-69", "70-74", "75-79", "80+"],
            age_data=[0, 0, 0, 0, 0],
            monthly_labels=["ม.ค.", "ก.พ.", "มี.ค."],
            monthly_data=[0, 0, 0],
            avg_age=0,
            avg_assessment=0,
            risk_rate=0,
        )
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return str(e)

@doctor_bp.get("/duty/events")
def doctor_duty_events():
    if not _guard_doctor(): return jsonify([]), 401
    supabase = get_db_connection()
    doctor_id = session.get("user_id")
    try:
        resp = supabase.table("doctor_duty_events").select("*").eq("doctor_id", doctor_id).execute()
        events = []
        for r in resp.data:
            events.append({
                "id": r["id"],
                "title": r["title"],
                "start": r["start_datetime"],
                "end": r["end_datetime"]
            })
        return jsonify(events)
    except:
        return jsonify([])

@doctor_bp.post("/duty/create")
def doctor_duty_create():
    if not _guard_doctor(): return jsonify({"ok": False}), 401
    supabase = get_db_connection()
    data = request.get_json() or request.form.to_dict()
    
    try:
        insert_data = {
            "doctor_id": session.get("user_id"),
            "title": data.get("title", "Day"),
            "start_datetime": data.get("start"),
            "end_datetime": data.get("end"),
            "note": data.get("note")
        }
        resp = supabase.table("doctor_duty_events").insert(insert_data).execute()
        new_event = resp.data[0]
        return jsonify({"ok": True, "id": new_event["id"]})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

@doctor_bp.get("/patients")
def patients():
    if not _guard_doctor(): return redirect(url_for("doctor.login"))
    return render_template("doctor/medical_patients.html")

@doctor_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))