from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db.db import get_db_connection
from datetime import date

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

def _guard_nurse():
    return session.get("role") == "nurse" and session.get("user_id")

@nurse_bp.get("/")
def index():
    if _guard_nurse():
        return redirect(url_for("nurse.dashboard"))
    return redirect(url_for("auth.login"))

@nurse_bp.get("/dashboard")
def dashboard():
    if not _guard_nurse():
        return redirect(url_for("auth.login"))

    supabase = get_db_connection()
    kpis = {"today": 0, "week": 0, "month": 0, "year": 0, "total": 0}

    try:
        # Total Patients
        kpis["total"] = supabase.table("patients").select("*", count="exact").execute().count
        
        # Today's encounters
        today = date.today().isoformat()
        kpis["today"] = supabase.table("encounters").select("*", count="exact").eq("encounter_date", today).execute().count

        return render_template(
            "nurse/dashboard.html",
            kpis=kpis,
            chart_data={}
        )
    except Exception as e:
        print(f"Nurse Dashboard Error: {e}")
        flash("เกิดข้อผิดพลาดในการดึงข้อมูล", "error")
        return render_template("nurse/dashboard.html", kpis=kpis)

@nurse_bp.get("/patients")
def patients_list():
    if not _guard_nurse():
        return redirect(url_for("auth.login"))
    
    supabase = get_db_connection()
    try:
        resp = supabase.table("patients").select("*").order("created_at", desc=True).limit(50).execute()
        return render_template("nurse/patients.html", patients=resp.data)
    except:
        return render_template("nurse/patients.html", patients=[])

@nurse_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))