from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from db.db import get_db_connection
from datetime import date, datetime

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

    supabase = get_db_connection()
    today_obj = date.today()
    
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return render_template(
            "admin/dashboard.html", 
            today=today_obj,
            stats={"users":0,"patients":0,"today_patients":0,"appointments_today":0,"assessments_today":0}, 
            latest_users=[], 
            active_page="dashboard"
        )

    try:
        # Get Stats with safe error handling for missing tables
        def safe_get_count(table_name, filter_func=None):
            try:
                query = supabase.table(table_name).select("*", count="exact")
                if filter_func:
                    query = filter_func(query)
                return query.execute().count or 0
            except:
                return 0

        users_count = safe_get_count("users")
        patients_count = safe_get_count("patients")
        
        today_iso = today_obj.isoformat()
        today_patients = safe_get_count("patients", lambda q: q.gte("created_at", today_iso))
        
        today_start = datetime.combine(today_obj, datetime.min.time()).isoformat()
        today_end = datetime.combine(today_obj, datetime.max.time()).isoformat()
        today_appts = safe_get_count("appointments", lambda q: q.gte("appt_datetime", today_start).lte("appt_datetime", today_end))
        
        # Latest users
        latest_users = []
        try:
            resp = supabase.table("users").select("username, role, created_at").order("created_at", desc=True).limit(5).execute()
            latest_users = resp.data
        except:
            pass

        stats = {
            "users": users_count,
            "patients": patients_count,
            "today_patients": today_patients,
            "appointments_today": today_appts,
            "assessments_today": 0,
        }

        return render_template(
            "admin/dashboard.html",
            today=today_obj,
            username=session.get("username"),
            stats=stats,
            latest_users=latest_users,
            range_key="month",
            weekly_labels=["สัปดาห์ 1", "สัปดาห์ 2", "สัปดาห์ 3", "สัปดาห์ 4"],
            weekly_values=[0, 0, 0, 0],
            type_labels=["ติดตามอาการ", "ประเมิน CGA", "อื่นๆ"],
            type_values=[0, 0, 0],
            active_page="dashboard",
        )
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return render_template(
            "admin/dashboard.html", 
            today=today_obj,
            stats={"users":0,"patients":0,"today_patients":0,"appointments_today":0,"assessments_today":0}, 
            latest_users=[], 
            active_page="dashboard"
        )

# --- PATIENTS ---
@admin_bp.get("/patients")
def patients_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    q = (request.args.get("q") or "").strip()
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    try:
        query = supabase.table("patients").select("*", count="exact")
        if q: query = query.ilike("full_name", f"%{q}%")
        resp = query.order("created_at", desc=True).range(offset, offset + per_page - 1).execute()
        
        total_rows = resp.count or 0
        total_pages = max((total_rows + per_page - 1) // per_page, 1)

        return render_template("admin/patients.html", patients=resp.data, q=q, page=page, total_pages=total_pages, active_page="patients")
    except Exception as e:
        print(f"Patients Error: {e}")
        return render_template("admin/patients.html", patients=[], q=q, page=1, total_pages=1, active_page="patients")

@admin_bp.post("/patients/add")
def add_patient():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    data = {
        "hn": request.form.get("hn"),
        "full_name": request.form.get("full_name"),
        "gender": request.form.get("gender"),
        "birth_date": request.form.get("birth_date") or None,
        "phone": request.form.get("phone"),
        "address": request.form.get("address"),
    }
    try:
        supabase.table("patients").insert(data).execute()
        flash("เพิ่มข้อมูลผู้ป่วยสำเร็จ", "success")
    except Exception as e:
        flash(f"เพิ่มข้อมูลไม่สำเร็จ: {e}", "error")
    return redirect(url_for("admin.patients_list"))

@admin_bp.post("/patients/delete/<int:id>")
def delete_patient(id: int):
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    try:
        supabase.table("patients").delete().eq("id", id).execute()
        flash("ลบข้อมูลผู้ป่วยสำเร็จ", "success")
    except Exception as e:
        flash(f"ลบข้อมูลไม่สำเร็จ: {e}", "error")
    return redirect(url_for("admin.patients_list"))

# --- DOCTORS ---
@admin_bp.get("/doctors")
def doctors_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    try:
        resp = supabase.table("users").select("*").eq("role", "doctor").order("full_name").execute()
        return render_template("admin/doctors.html", doctors=resp.data, active_page="doctors")
    except:
        return render_template("admin/doctors.html", doctors=[], active_page="doctors")

# --- NURSES ---
@admin_bp.get("/nurses")
def nurses_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    try:
        resp = supabase.table("users").select("*").eq("role", "nurse").order("full_name").execute()
        return render_template("admin/nurses.html", nurses=resp.data, active_page="nurses")
    except:
        return render_template("admin/nurses.html", nurses=[], active_page="nurses")

# --- APPOINTMENTS ---
@admin_bp.get("/appointments")
def appointments_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    try:
        resp = supabase.table("appointments").select("*, patients(hn, full_name)").order("appt_datetime", desc=True).limit(100).execute()
        return render_template("admin/appointments.html", appointments=resp.data, active_page="appointments")
    except:
        return render_template("admin/appointments.html", appointments=[], active_page="appointments")

# --- CGA ASSESSMENTS ---
@admin_bp.get("/assessments")
def assessments_list():
    if not _require_admin(): return redirect(url_for("auth.login"))
    supabase = get_db_connection()
    try:
        resp = supabase.table("cga_headers").select("*, encounters(*, patients(hn, full_name))").order("assessment_date", desc=True).limit(100).execute()
        return render_template("admin/assessments.html", assessments=resp.data, active_page="assessments")
    except:
        return render_template("admin/assessments.html", assessments=[], active_page="assessments")

@admin_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))