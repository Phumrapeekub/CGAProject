from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
from db.db import get_db_client, get_db_connection
from datetime import datetime, date, timedelta
from ml.hmm_predictor import predictor # ✅ Import real AI model
from linebot import LineBotApi
from linebot.models import TextSendMessage
from flask_login import login_required # type: ignore
import os
import re
import pandas as pd

# Line Setup
line_bot_api = None
if os.getenv("LINE_CHANNEL_ACCESS_TOKEN"):
    line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))


# ==============================
# HELPERS
# ==============================
def _guard_doctor() -> bool:
    return bool(session.get("logged_in")) and (str(session.get("role") or "").lower() == "doctor")


def _thai_months_full():
    return [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    ]


def _thai_months_short():
    return ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def format_thai_short_with_year(d: date) -> str:
    m = _thai_months_full()[d.month - 1]
    y = d.year + 543
    return f"{d.day} {m[:3]} {y}"


def _safe_dt_str(dt):
    if not dt:
        return "-"
    try:
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)


def _parse_iso(dt_str: str):
    """
    Robustly parse ISO datetime string using pandas for maximum compatibility.
    Returns datetime object or None if parsing fails.
    """
    if not dt_str: return None
    if isinstance(dt_str, datetime): return dt_str
    if isinstance(dt_str, date): return datetime(dt_str.year, dt_str.month, dt_str.day)
    
    import pandas as pd
    try:
        ts = pd.to_datetime(dt_str)
        if pd.isna(ts): return None
        return ts.to_pydatetime()
    except:
        return None


def _detect_gender(name: str) -> str:
    """Detect gender from Thai name prefixes or common name patterns"""
    if not name: return ""
    name = str(name).strip()
    # Direct prefixes
    if name.startswith("นาย"): return "ชาย"
    if name.startswith("นาง") or name.startswith("น.ส.") or name.startswith("นางสาว"): return "หญิง"
    
    # Common name patterns (Heuristic fallback)
    # If the user mentioned "ทีปกร" specifically as male
    if name.startswith("ทีปกร"): return "ชาย"
    
    return ""


doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


@doctor_bp.post("/patient/<hn>/update_line")
def update_line_id(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
        
    line_user_id = (request.form.get("line_user_id") or "").strip()
    
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        supabase.table("patients").update({"line_user_id": line_user_id if line_user_id else None}).eq("hn", hn).execute()
        flash("อัปเดต Line User ID เรียบร้อยแล้ว", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        
    return redirect(url_for("doctor.patient_detail", hn=hn))


# ==============================
# AUTH
# ==============================
@doctor_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        # --- 🔓 Emergency Bypass สำหรับ doctor1 (ใช้ Hash จริง) ---
        DOCTOR_HASH = "scrypt:32768:8:1$clBDnyu6f6uKaSPR$6c9b9807c5a35fe6facca667ae66036d1377cf1b752d1d8883a46bb855372e418a9570e8ab9fac9d36dcaa3a82e5f6ed1ff8b1928093da66dd412f251359a2db"
        if username == "doctor1" and check_password_hash(DOCTOR_HASH, password):
            session.clear()
            session["logged_in"] = True
            session["user_id"] = 2
            session["username"] = "doctor1"
            session["full_name"] = "พญ.ลีลาวดี กลิ่นหอม"
            session["role"] = "doctor"
            return redirect(url_for("doctor.dashboard"))

        from db.db import get_db_client, get_db_connection
        supabase = get_db_client()
        if not supabase:
            flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
            return redirect(url_for("doctor.login"))

        try:
            res = supabase.table("users").select("id, username, password_hash, role, is_active, full_name")\
                .eq("username", username).limit(1).execute()
            user = res.data[0] if res.data else None
            
            role_db = (user.get("role") if user else "") or ""
            role_db = role_db.strip().lower()

            ok = (
                user
                and (str(user.get("is_active")).lower() in ['true', '1'])
                and role_db == "doctor"
                and user.get("password_hash")
                and check_password_hash(user["password_hash"], password)
            )

            if not ok:
                flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
                return redirect(url_for("doctor.login"))

            session.clear()
            session["logged_in"] = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user.get("full_name") or user["username"]
            session["role"] = role_db
            return redirect(url_for("doctor.dashboard"))
        except Exception as e:
            print(f"❌ Login Error: {e}")
            flash("เกิดข้อผิดพลาดในการเข้าสู่ระบบ", "error")
            return redirect(url_for("auth.login"))

    return render_template(
        "auth/login.html",
        role_label="แพทย์",
        page_title="Doctor Login",
        page_desc="กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ",
        post_url=url_for("doctor.login"),
        logo_path=url_for("static", filename="logo_phayao.png"),
    )


@doctor_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ==============================
# PROFILE
# ==============================
@doctor_bp.get("/profile")
def profile():
    if not _guard_doctor():
        return redirect(url_for("auth.login"))

    user_id = session.get("user_id")
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("doctor.dashboard"))

    try:
        res = supabase.table("users").select("*").eq("id", user_id).single().execute()
        user_data = res.data
        if not user_data:
            flash("ไม่พบข้อมูลผู้ใช้", "error")
            return redirect(url_for("doctor.dashboard"))

        return render_template("doctor/medical_profile.html", user=user_data)
    except Exception as e:
        print(f"❌ Profile Error: {e}")
        flash("เกิดข้อผิดพลาดในการดึงข้อมูลโปรไฟล์", "error")
        return redirect(url_for("doctor.dashboard"))


# ==============================
# DASHBOARD
# ==============================
@doctor_bp.get("/dashboard")
def dashboard():
    if not _guard_doctor():
        return redirect(url_for("auth.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    
    # รับพารามิเตอร์การกรองวันที่
    filter_type = request.args.get("filter", "today")
    selected_date_str = request.args.get("date")
    
    today = date.today()
    start_date = today
    end_date = today

    import calendar
    if filter_type == "today":
        start_date = today
        end_date = today
    elif filter_type == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif filter_type == "month":
        if selected_date_str and len(selected_date_str) >= 7:
            try:
                start_date = datetime.strptime(selected_date_str[:7], "%Y-%m").date()
            except:
                start_date = today.replace(day=1)
        else:
            start_date = today.replace(day=1)
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        end_date = start_date.replace(day=last_day)
    elif filter_type == "custom" and selected_date_str:
        try:
            start_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
            end_date = start_date
        except:
            start_date = today
            end_date = today

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # กำหนดค่าเริ่มต้น (Default values) เผื่อดึงข้อมูลไม่ได้
    kpis = {
        "total_patients": 0, "today_patients": 0, "month_patients": 0, "year_patients": 0,
        "pending_patients": 0, "today_appointments": 0, "high_risk": 0,
        "total_unique_patients": 0, "completed_patients_today": 0, "avg_cga_score": 0, "delta_avg_month": 0,
    }
    latest_assessments = []
    today_appointments = []
    risk_labels = ["เสี่ยงสูง", "เสี่ยงปานกลาง", "เสี่ยงต่ำ"]
    risk_data = [0, 0, 0]
    age_labels = ["60-64", "65-69", "70-74", "75-79", "80+"]
    age_data = [0, 0, 0, 0, 0]
    monthly_labels = _thai_months_short()
    monthly_data = [0] * 12
    avg_age = 0

    # ช่วงเวลาสำหรับ Card เดือนนี้ (Default คือเดือนปัจจุบัน)
    m_start_current = today.replace(day=1).isoformat()
    m_last_day_current = calendar.monthrange(today.year, today.month)[1]
    m_end_current = today.replace(day=m_last_day_current).isoformat()

    if not supabase:
        flash("เชื่อมต่อฐานข้อมูลไม่ได้ (แสดงโหมดออฟไลน์)", "warning")
        return render_template(
            "doctor/medical_dashboard.html",
            kpis=kpis, latest_assessments=latest_assessments, today_appointments=today_appointments,
            risk_labels=risk_labels, risk_data=risk_data, age_labels=age_labels, age_data=age_data,
            monthly_labels=monthly_labels, monthly_data=monthly_data, avg_age=avg_age,
            avg_assessment=0, risk_rate=0,
            filter_type=filter_type, selected_date=start_str,
            today_str=today.isoformat(),
            start_date=start_str, end_date=end_str,
            month_start=m_start_current, month_end=m_end_current
        )

    try:
        doctor_id = session.get("user_id")
        today = date.today()
        today_str = today.isoformat()

        # =========================
        # 1) KPIs
        # =========================
        def get_count(table, filter_col=None, filter_val=None):
            try:
                q = supabase.table(table).select("*", count="exact")
                if filter_col:
                    q = q.eq(filter_col, filter_val)
                res = q.limit(0).execute()
                return res.count or 0
            except:
                return 0

        total_patients = get_count("patients")

        # คำนวณจำนวนผู้ป่วยตามช่วงที่เลือก (สำหรับ Card วันนี้/สัปดาห์/เลือกเอง)
        res_range = supabase.table("encounters") \
            .select("patient_id") \
            .gte("encounter_date", start_str) \
            .lte("encounter_date", end_str) \
            .execute()
        date_patient_count = len(set(r["patient_id"] for r in (res_range.data or [])))
        
        date_label_th = "วันนี้"
        if filter_type == "week": date_label_th = "สัปดาห์นี้"
        elif filter_type == "custom": date_label_th = f"วันที่ {format_thai_short_with_year(start_date)}"
        elif filter_type == "month": date_label_th = f"เดือน {_thai_months_full()[start_date.month-1]} {start_date.year + 543}"

        today_patients = date_patient_count

        # ผู้ป่วยเดือนนี้ (สำหรับ Card เดือนนี้)
        res_month = supabase.table("encounters") \
            .select("patient_id") \
            .gte("encounter_date", m_start_current) \
            .lte("encounter_date", m_end_current) \
            .execute()
        month_patients = len(set(r["patient_id"] for r in (res_month.data or [])))

        # High risk
        res_hr = supabase.table("assessment_scores") \
            .select("*", count="exact") \
            .ilike("risk_level", "%สูง%") \
            .execute()
        high_risk = res_hr.count or 0

        # นัดหมายวันนี้
        res_appts_count = supabase.table("appointments") \
            .select("*", count="exact") \
            .eq("created_by_doctor", doctor_id) \
            .eq("status", "scheduled") \
            .gte("appt_datetime", today_str) \
            .lt("appt_datetime", (today + timedelta(days=1)).isoformat()) \
            .execute()
        today_appointments_count = res_appts_count.count or 0

        # =========================
        # 2) ดึงผู้ป่วยทั้งหมดทำ map (เสถียรสุด)
        # =========================
        res_all_patients = supabase.table("patients") \
            .select("id, hn, full_name, birth_date") \
            .execute()
        
        p_list = res_all_patients.data or []

        p_map = {
            str(p["id"]): p
            for p in p_list
        }

        # =========================
        # 3) การประเมินล่าสุด (ดึงจาก cga_records จริง)
        # =========================
        res_latest_assess = (
            supabase
            .table("cga_records")
            .select("*, patients(full_name, hn)")
            .order("id", desc=True)
            .limit(5)
            .execute()
        )

        latest_assessments = []
        for r in (res_latest_assess.data or []):
            p_info = r.get("patients") or {}
            name = (p_info.get("full_name") or r.get("full_name") or "ไม่ระบุชื่อ").strip()
            hn = p_info.get("hn") or r.get("hn") or "-"
            
            # Scores
            m_score = r.get("mmse_score")
            t_score = r.get("tgds_score")
            
            # Date
            d_str = r.get("assessed_date") or r.get("created_at")
            d_obj = None
            if d_str:
                try:
                    if 'T' in d_str: d_obj = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
                    else: d_obj = datetime.strptime(d_str[:10], "%Y-%m-%d")
                except: pass

            # Risk Logic (Refined for Dashboard Table)
            # Confirmed column: 'suicide_risk'
            sra_val = 0
            try:
                s_raw = r.get("suicide_risk")
                if s_raw:
                    if str(s_raw).lower() in ['มี', 'yes', 'true']:
                        sra_val = 17 # Force high risk
                    elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']:
                        sra_val = 0
                    else:
                        sra_val = int(float(s_raw))
            except:
                sra_val = 0

            risk_slug = 'low'
            risk_label = 'ปกติ'
            
            if sra_val >= 17 or (t_score is not None and t_score >= 6) or (m_score is not None and m_score <= 21):
                risk_slug = 'high'
                risk_label = 'เสี่ยงสูง'
            elif sra_val >= 9 or (t_score is not None and t_score >= 4) or (m_score is not None and m_score <= 25):
                risk_slug = 'medium'
                risk_label = 'เสี่ยงปานกลาง'

            latest_assessments.append({
                "hn": hn,
                "full_name": name,
                "date_th": format_thai_short_with_year(d_obj) if d_obj else "-",
                "mmse_score": m_score if m_score is not None else '-',
                "tgds_score": t_score if t_score is not None else '-',
                "risk_level": risk_label,
                "risk_level_slug": risk_slug
            })

        # =========================
        # 4) นัดหมายวันนี้
        # =========================
        res_today_appts = supabase.table("appointments") \
            .select("*") \
            .eq("created_by_doctor", doctor_id) \
            .eq("status", "scheduled") \
            .gte("appt_datetime", today_str) \
            .lt("appt_datetime", (today + timedelta(days=1)).isoformat()) \
            .order("appt_datetime") \
            .limit(10) \
            .execute()

        today_appointments = []
        for a in (res_today_appts.data or []):
            p = p_map.get(str(a.get("patient_id")), {})
            appt_dt = datetime.fromisoformat(a["appt_datetime"].replace("Z", "+00:00"))

            today_appointments.append({
                "patient_id": a.get("patient_id"),
                "hn": p.get("hn") or "-",
                "full_name": (p.get("full_name") or "ไม่ระบุชื่อ").strip(),
                "time": appt_dt.strftime("%H:%M"),
                "note": a.get("note") or "-",
            })

        # =========================
        # 5) Charts (Real Data)
        # =========================
        # Risk Distribution Logic
        risk_counts = {"high": 0, "medium": 0, "low": 0}
        age_bins = {"60-64": 0, "65-69": 0, "70-74": 0, "75-79": 0, "80+": 0}
        
        # Get all patients with their scores for distribution
        res_all_p = supabase.table("cga_records").select("mmse_score, tgds_score, suicide_risk, age").execute()
        for row in (res_all_p.data or []):
            m = row.get("mmse_score")
            t = row.get("tgds_score")
            
            s = 0
            try:
                s_raw = row.get("suicide_risk")
                if s_raw:
                    if str(s_raw).lower() in ['มี', 'yes', 'true']:
                        s = 17
                    elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']:
                        s = 0
                    else:
                        s = int(float(s_raw))
            except:
                s = 0
            
            age_val = row.get("age")
            
            # Refined Risk Determination
            if s >= 17 or (t is not None and t >= 6) or (m is not None and m <= 21):
                risk_counts["high"] += 1
            elif s >= 9 or (t is not None and t >= 4) or (m is not None and m <= 25):
                risk_counts["medium"] += 1
            else:
                risk_counts["low"] += 1
                
            # Determine Age Bin
            try:
                if age_val:
                    age_int = int(float(age_val))
                    if 60 <= age_int <= 64: age_bins["60-64"] += 1
                    elif 65 <= age_int <= 69: age_bins["65-69"] += 1
                    elif 70 <= age_int <= 74: age_bins["70-74"] += 1
                    elif 75 <= age_int <= 79: age_bins["75-79"] += 1
                    elif age_int >= 80: age_bins["80+"] += 1
            except: pass

        risk_labels = ["เสี่ยงสูง", "เสี่ยงปานกลาง", "เสี่ยงต่ำ"]
        risk_data = [risk_counts["high"], risk_counts["medium"], risk_counts["low"]]

        age_labels = ["60-64", "65-69", "70-74", "75-79", "80+"]
        age_data = [age_bins["60-64"], age_bins["65-69"], age_bins["70-74"], age_bins["75-79"], age_bins["80+"]]

        monthly_labels = _thai_months_short()
        monthly_data = [0] * 12
        # Fill monthly data from encounters
        res_enc_all = supabase.table("encounters").select("encounter_date").execute()
        for enc in (res_enc_all.data or []):
            try:
                dt = datetime.strptime(enc["encounter_date"], "%Y-%m-%d")
                if dt.year == today.year:
                    monthly_data[dt.month - 1] += 1
            except: pass

        kpis = {
            "total_patients": total_patients,
            "today_patients": today_patients,
            "month_patients": month_patients,
            "year_patients": month_patients,
            "pending_patients": total_patients - today_patients,
            "today_appointments": today_appointments_count,
            "high_risk": risk_counts["high"],
            "total_unique_patients": total_patients,
            "completed_patients_today": today_patients,
            "avg_cga_score": 0, # Could calc sum/count if needed
            "delta_avg_month": 0,
        }

        # Calculate averages for bottom row
        total_age = 0
        p_count = 0
        for p in p_list:
            try:
                # Calculate age from birth_date since age_year is missing in DB
                bd = p.get("birth_date")
                if bd:
                    if isinstance(bd, str):
                        bd_dt = datetime.strptime(bd[:10], "%Y-%m-%d").date()
                    else:
                        bd_dt = bd
                    age = today.year - bd_dt.year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
                    total_age += age
                    p_count += 1
            except Exception as e:
                print(f"Age Calc Error: {e}")
                pass
        avg_age = round(total_age / p_count, 1) if p_count > 0 else 0
        
        return render_template(
            "doctor/medical_dashboard.html",
            kpis=kpis,
            latest_assessments=latest_assessments,
            today_appointments=today_appointments,
            risk_labels=risk_labels,
            risk_data=risk_data,
            age_labels=age_labels,
            age_data=age_data,
            monthly_labels=monthly_labels,
            monthly_data=monthly_data,
            avg_age=avg_age,
            avg_assessment=1.5,
            risk_rate=round((risk_counts["high"] / total_patients * 100), 1) if total_patients > 0 else 0,
            filter_type=filter_type,
            selected_date=start_str,
            date_patient_count=date_patient_count,
            date_label_th=date_label_th,
            month_patient_count=month_patients,
            today_str=today_str,
            start_date=start_str,
            end_date=end_str,
            month_start=m_start_current,
            month_end=m_end_current
        )

    except Exception as e:
        print("❌ Dashboard Error:", e)
        flash("เกิดข้อผิดพลาดในการโหลด Dashboard", "error")
        return redirect(url_for("doctor.login"))


# ==============================
# PATIENTS LIST
# ==============================
@doctor_bp.get("/patients")
def patients():
    if not _guard_doctor():
        return redirect(url_for("auth.login"))

    hn_q = (request.args.get("hn") or "").strip()
    name_q = (request.args.get("name") or "").strip()
    date_q = (request.args.get("date") or "").strip()
    start_q = (request.args.get("start_date") or "").strip()
    end_q = (request.args.get("end_date") or "").strip()

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("auth.login"))

    try:
        # 1. Fetch Patients
        query = supabase.table("patients").select("*")

        if date_q:
            start_q = date_q
            end_q = date_q

        if start_q:
            q_e = supabase.table("encounters").select("patient_id").gte("encounter_date", start_q)
            if end_q:
                q_e = q_e.lte("encounter_date", end_q)
            res_e = q_e.execute()
            
            p_ids = list(set(r["patient_id"] for r in (res_e.data or [])))
            if p_ids:
                query = query.in_("id", p_ids)
            else:
                return render_template("doctor/medical_patients.html", patients=[], date_q=date_q or start_q)

        if hn_q:
            query = query.ilike("hn", f"%{hn_q}%")
        if name_q:
            query = query.ilike("full_name", f"%{name_q}%")

        res = query.order("created_at", desc=True).execute()
        rows = res.data or []
        
        if not rows:
             return render_template("doctor/medical_patients.html", patients=[])

        hns = [p["hn"] for p in rows if p.get("hn")]

        # 2. Fetch Latest CGA Records for these patients (The source of truth)
        cga_map = {}
        disease_map = {}

        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            if hns:
                format_strings = ','.join(['%s'] * len(hns))
                query_sql = f'''
                    SELECT p.hn, a.answer_text
                    FROM patients p
                    JOIN encounters e ON p.id = e.patient_id
                    JOIN cga_headers c ON e.id = c.encounter_id
                    JOIN assessment_answers a ON c.session_id = a.session_id
                    WHERE p.hn IN ({format_strings})
                      AND a.instrument = 'basic' 
                      AND (a.answer_text LIKE 'chronicDiseases:%' OR a.answer_text LIKE 'otherDisease:%')
                '''
                cur.execute(query_sql, tuple(hns))
                for mr in cur.fetchall():
                    mhn = mr['hn']
                    ans = mr['answer_text']
                    if ':' in ans:
                        _, v = ans.split(':', 1)
                        if v.strip() and v.strip() != '-':

                            if mhn not in disease_map:
                                disease_map[mhn] = []
                            # Translate common diseases to Thai
                            raw_ds = v.strip().split(',')
                            for rd in raw_ds:
                                clean_rd = rd.strip().lower()
                                th_d = clean_rd
                                if clean_rd == 'diabetes': th_d = 'เบาหวาน'
                                elif clean_rd == 'hypertension': th_d = 'ความดันโลหิตสูง'
                                elif clean_rd == 'heart': th_d = 'โรคหัวใจ'
                                elif clean_rd == 'kidney': th_d = 'โรคไต'
                                elif clean_rd == 'cancer': th_d = 'มะเร็ง'
                                else: th_d = rd.strip()
                                disease_map[mhn].append(th_d)

            cur.close()
            conn.close()
        except Exception as e:
            print(f"DEBUG: MySQL disease fetch error: {e}")

        history_map = {}  # ✅ Group history to pass to AI
        consult_map = {}
        try:
            if hns:
                # Fetch all records for these HNs to get history
                res_cga = supabase.table("cga_records") \
                    .select("hn, assessed_date, mmse_score, tgds_score, suicide_risk, created_at") \
                    .in_("hn", hns) \
                    .execute()
                
                all_records = res_cga.data or []
                # Sort by date ascending for the history sequence
                all_records.sort(key=lambda x: x.get("assessed_date") or x.get("created_at") or "")
                
                for c in all_records:
                    thn = str(c.get("hn") or "").strip()
                    if not thn: continue
                    
                    # For history (sequence)
                    if thn not in history_map: history_map[thn] = []
                    if c.get("mmse_score") is not None:
                        history_map[thn].append(float(c["mmse_score"]))
                    
                    # For latest (map)
                    cga_map[thn] = c

                # Fetch latest consultation (include more fields for better risk detection)
                res_cons = supabase.table("consultations") \
                    .select("hn, note_from_nurse, mmse_score, tgds_score, depression_2q, created_at") \
                    .in_("hn", hns) \
                    .order("created_at", desc=True) \
                    .execute()
                
                for c in (res_cons.data or []):
                    thn = str(c.get("hn") or "").strip()
                    if thn and thn not in consult_map:
                        consult_map[thn] = c

        except Exception as e:
            print(f"⚠️ Warning: Could not fetch cga/consult records for list: {e}")

        today = date.today()
        out = []

        for r in rows:
            curr_hn = str(r.get("hn") or "").strip()
            if curr_hn.upper().startswith("TMP"):
                continue

            # Calculate Age

            bd_str = r.get("birth_date")
            age = "-"
            if bd_str:
                try:
                    bd_dt = datetime.strptime(str(bd_str)[:10], "%Y-%m-%d").date()
                    b_year = bd_dt.year
                    if b_year > 2400: b_year -= 543
                    age_val = today.year - b_year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
                    age = max(0, age_val)
                except: pass

            curr_hn = str(r.get("hn") or "").strip()
            cga = cga_map.get(curr_hn, {})
            cons = consult_map.get(curr_hn, {})


            # Map Columns: Fallback between cga_records, MySQL, and consultations
            d_list = disease_map.get(curr_hn)
            if d_list:
                disease = ", ".join(d_list)
            else:
                disease = cons.get("note_from_nurse") or "-"

            
            # Scores (Fallback)
            mmse = cga.get("mmse_score") if cga.get("mmse_score") is not None else cons.get("mmse_score")
            tgds = cga.get("tgds_score") if cga.get("tgds_score") is not None else cons.get("tgds_score")
            
            # Date from latest record
            last_date = "-"
            d_raw = cga.get("assessed_date") or cga.get("created_at") or cons.get("created_at")
            if d_raw:
                try:
                    dt = pd.to_datetime(d_raw)
                    last_date = format_thai_short_with_year(dt.date())
                except:
                    last_date = str(d_raw)[:10]

            # Risk Logic based on cga_records
            sra_val = 0
            try:
                s_raw = cga.get("suicide_risk") or cons.get("depression_2q")
                if s_raw:
                    if str(s_raw).lower() in ['มี', 'yes', 'true']: sra_val = 17
                    elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']: sra_val = 0
                    else: sra_val = int(float(s_raw))
            except: pass

            # Risk Logic: Use AI Predictor for consistency
            risk_slug = "low"
            try:
                # 1. Prepare data for predictor
                hist = history_map.get(curr_hn, [])
                pred_data = {
                    "hn": curr_hn,
                    "mmse_score": mmse,
                    "mmse_scores": hist, 
                    "tgds_score": tgds,
                    "age": age if isinstance(age, int) else 70,
                    "chronic_count": 1 if r.get("chronic_disease") else 0
                }
                
                is_dementia = False
                risk_score_ai = 0
                prediction = {}
                
                if mmse is not None or hist:
                    prediction = predictor.predict(pred_data)
                    is_dementia = (prediction.get("result") == "Dementia")
                    risk_score_ai = prediction.get("risk_score", 0)

                # --- UNIFIED CLINICAL RISK LOGIC (Sync with 3-state HMM) ---
                
                # A. Dementia Score (HMM 3-state: 0-5 scale)
                clinical_dementia_score = risk_score_ai
                
                # B. Suicide Risk (Weighted to match 0-5 scale roughly)
                sra_score = 0
                if sra_val >= 17: sra_score = 4.5 + min(0.5, (sra_val - 17) * 0.05)
                elif sra_val >= 9: sra_score = 2.5 + (sra_val - 9) * 0.2

                # C. Depression Score (Weighted to match 0-5 scale)
                dep_score = 0
                tgds_val = tgds if tgds is not None else 0
                if tgds_val >= 10: dep_score = 3.75 + (tgds_val - 10) * 0.25
                elif tgds_val >= 5: dep_score = 2.0 + (tgds_val - 5) * 0.35
                
                # Final Display Score (Max of all risks)
                final_score = max(clinical_dementia_score, sra_score, dep_score)

                # Determine Slug based on 3-state logic
                # HIGH: Dementia OR High Suicide/Depression
                if (prediction.get("state") == "Dementia") or sra_val >= 17 or tgds_val >= 10 or final_score >= 3.75:
                    risk_slug = "high"
                # MEDIUM: MCI OR Moderate Suicide/Depression
                elif (prediction.get("state") == "MCI") or sra_val >= 9 or tgds_val >= 5 or (mmse is not None and mmse <= 24) or final_score >= 2.0:
                    risk_slug = "medium"
                else:
                    risk_slug = "low"

            except Exception as e:
                print(f"⚠️ Prediction failed for {curr_hn}: {e}")
                if sra_val >= 17 or (tgds is not None and int(tgds) >= 10):
                    risk_slug = "high"
                elif sra_val >= 9 or (tgds is not None and int(tgds) >= 5):
                    risk_slug = "medium"

            out.append({
                "hn": curr_hn,
                "gcn": r.get("gcn"),
                "full_name": (r.get("full_name") or "-").strip() or "-",
                "name": (r.get("full_name") or "-").strip() or "-",
                "gender": r.get("gender"),
                "age": age,
                "phone": r.get("phone"),
                "address": r.get("address"),
                
                "disease": disease,
                "last_assessed_date": last_date,
                "mmse": mmse,
                "tgds": tgds,
                "sra": sra_val,
                "risk_slug": risk_slug
            })

        return render_template("doctor/medical_patients.html", patients=out, date_q=date_q)
    except Exception as e:
        print(f"❌ Patients List Error: {e}")
        flash("เกิดข้อผิดพลาดในการดึงข้อมูลผู้ป่วย", "error")
        return render_template("doctor/medical_patients.html", patients=[])


# ==============================
# PATIENT DETAIL
# ==============================
@doctor_bp.get("/patient/<hn>", endpoint="patient_detail")
def patient_detail(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("doctor.patients"))

    try:
        # 1) patient
        res_p = supabase.table("patients").select("*").eq("hn", hn).limit(1).execute()
        patient = res_p.data[0] if (res_p.data and isinstance(res_p.data, list) and isinstance(res_p.data[0], dict)) else None

        if not patient:
            flash("ไม่พบผู้ป่วย", "error")
            return redirect(url_for("doctor.patients"))

        patient_id = patient.get("id")
        print(f"DEBUG: patient_id={patient_id}, hn={hn}")

        # --- Inject Age and Gender mapping for template ---
        today = date.today()
        bd_str = patient.get("birth_date")
        age = None
        if bd_str:
            try:
                bd_dt = datetime.strptime(str(bd_str)[:10], "%Y-%m-%d").date()
                b_year = bd_dt.year
                if b_year > 2400: b_year -= 543
                age_val = today.year - b_year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
                age = max(0, age_val)
            except: pass
        patient["age"] = age
        
        g = str(patient.get("gender") or "").lower()
        if g == "male" or g == "m": patient["gender_th"] = "ชาย"
        elif g == "female" or g == "f": patient["gender_th"] = "หญิง"
        else: patient["gender_th"] = g
        # --------------------------------------------------

        # 2) consultations
        try:
            res_cons = supabase.table("consultations").select("*").eq("hn", hn).order("id", desc=True).execute()
            print(f"DEBUG: res_cons.data raw type={type(res_cons.data)} val={res_cons.data}")
            consultations_data = res_cons.data
            if not isinstance(consultations_data, list):
                consultations_data = []
            # Sanitization
            consultations_data = [x for x in consultations_data if isinstance(x, dict)]
            print(f"DEBUG: consultations_data sanitized len={len(consultations_data)}")
        except Exception as e:
            print(f"DEBUG: consultations error: {e}")
            consultations_data = []
        
        # Helper to format date
        for c in consultations_data:
            if c.get("created_at"):
                c["created_at"] = _parse_iso(str(c["created_at"]))

        # ... (skip encounters/appts for brevity in replace block if possible, but context needed) ...
        # 3) visits = encounters
        res_e = supabase.table("encounters").select("*, users!encounters_created_by_fkey(full_name)").eq("patient_id", patient_id).order("created_at", desc=True).execute()
        enc_rows = res_e.data
        if not isinstance(enc_rows, list): enc_rows = []
        enc_rows = [x for x in enc_rows if isinstance(x, dict)]
        encounter_id = enc_rows[0]["id"] if enc_rows else None
        
        # Fetch doctor_notes for these encounters to show details in history cards
        enc_ids = [e['id'] for e in enc_rows]
        notes_map = {}
        if enc_ids:
            res_notes = supabase.table("doctor_notes").select("*").in_("encounter_id", enc_ids).execute()
            for n in (res_notes.data or []):
                # Keep the latest note per encounter
                if n['encounter_id'] not in notes_map:
                    notes_map[n['encounter_id']] = n

        visits = []
        for e in enc_rows:
            note_str = e.get("note") or ""
            chief = note_str.split("\n")[0].replace("CC:", "").strip() if note_str.startswith("CC:") else "บันทึกการตรวจ"
            
            # Get structured diagnosis and plan from doctor_notes
            dn = notes_map.get(e['id'], {})
            
            # ✅ กรองออก: ถ้าเป็นประเภท cga และไม่มีการบันทึกการวินิจฉัย ให้ซ่อนจากหน้านี้
            # เพราะจะไปแสดงที่ประวัติ CGA ด้านล่างแทน เพื่อไม่ให้คุณหมอสับสน
            is_cga = (e.get("encounter_type") == "cga")
            has_diagnosis = bool(dn.get("diagnosis") or dn.get("plan"))
            
            if is_cga and not has_diagnosis:
                continue

            visits.append({
                "id": e.get("id"),
                "chief_complaint": chief,
                "note": note_str,
                "diagnosis": dn.get("diagnosis"),
                "plan": dn.get("plan"),
                "status": (e.get("encounter_type") or "done"),
                "visit_datetime": _parse_iso(e.get("created_at")),
                "created_by": e.get("users!encounters_created_by_fkey", {}).get("full_name") or e.get("created_by"),
            })

        # 4) appointments
        # ...
        res_a = supabase.table("appointments").select("*").eq("patient_id", patient_id).order("appt_datetime", desc=True).execute()
        raw_appts = res_a.data
        if not isinstance(raw_appts, list): raw_appts = []
        raw_appts = [x for x in raw_appts if isinstance(x, dict)]
        upcoming_appts = []
        for a in raw_appts:
            a['appt_datetime'] = _parse_iso(a.get('appt_datetime'))
            upcoming_appts.append(a)

        # 6) CGA Records (Source of truth for assessments)
        cga_history = []
        try:
            res_cga = supabase.table("cga_records").select("*").eq("patient_id", patient_id).order("id", desc=True).execute()
            cga_history = res_cga.data or []
            if not cga_history and hn:
                res_cga_hn = supabase.table("cga_records").select("*").ilike("hn", hn).order("id", desc=True).execute()
                cga_history = res_cga_hn.data or []

            # Fetch session_id and risk from cga_headers for mapping
            # Use all encounter IDs for this patient to be comprehensive
            all_enc_ids = [e['id'] for e in enc_rows]
            headers_map = {}
            if all_enc_ids:
                res_headers = supabase.table("cga_headers").select("*").in_("encounter_id", all_enc_ids).execute()
                for h in (res_headers.data or []):
                    headers_map[h['encounter_id']] = h
            
            for c in cga_history:
                h_info = headers_map.get(c.get('encounter_id'), {})
                c['session_id'] = h_info.get('session_id')
                # If suicide_risk is missing in cga_records, try to get it from header risk_level
                if not c.get('suicide_risk'):
                    c['suicide_risk'] = h_info.get('risk_level')
        except Exception as e:
            print(f"DEBUG: CGA Fetch Error: {e}")

        # Data for Score Display & AI
        latest_cga = cga_history[0] if cga_history else {}
        latest_c = consultations_data[0] if consultations_data else {}

        # Fallback gender detection from prefix or name
        if not patient.get("gender") and patient.get("full_name"):
            patient["gender"] = _detect_gender(patient["full_name"])

        # Age Calculation
        today = date.today()
        bd_str = patient.get("birth_date")
        p_age = 60 # fallback
        if bd_str:
            try:
                bd_dt = datetime.strptime(str(bd_str)[:10], "%Y-%m-%d").date()
                p_age = today.year - bd_dt.year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
            except: pass

# 5) Real AI analysis using HMM model (3-state version)
        ai_analysis = {}
        try:
            predictor.set_supabase(supabase)
            
            def _get_score(d1, d2, key):
                v1 = d1.get(key)
                if v1 is not None: return v1
                return d2.get(key)

            # ✅ ส่ง patient_id เพื่อให้ดึงประวัติ MMSE จาก cga_records
            p_data = {
                "patient_id": patient_id,
                "hn": hn,
                "mmse_score": _get_score(latest_cga, latest_c, "mmse_score"),
                "tgds_score": _get_score(latest_cga, latest_c, "tgds_score"),
                "education": latest_cga.get("education") or latest_c.get("education") or "primary",
            }
            
            prediction = predictor.predict(p_data)
            
            if "error" not in prediction:
                # 3-state HMM: Normal(0), MCI(1), Dementia(2) -> Scale 0-5
                risk_score_display = prediction.get("risk_score", 0) 
                
                # Fetch SRA and TGDS for unified risk check
                sra_val = 0
                try:
                    s_raw = latest_cga.get("suicide_risk")
                    if s_raw:
                        if str(s_raw).lower() in ['มี', 'yes', 'true']: sra_val = 17
                        elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']: sra_val = 0
                        else: sra_val = int(float(s_raw))
                except: pass
                
                tgds_val = float(p_data.get("tgds_score") or 0)
                mmse_val = float(p_data.get("mmse_score") or 0)

                # --- UNIFIED CLINICAL RISK LOGIC (Scaled to 0-5) ---
                
                # A. Dementia Score
                clinical_dementia_score = risk_score_display
                
                # B. Suicide Risk (Scaled to 0-5)
                sra_score = 0
                if sra_val >= 17: sra_score = 4.5 + min(0.5, (sra_val - 17) * 0.05)
                elif sra_val >= 9: sra_score = 2.5 + (sra_val - 9) * 0.2
                
                # C. Depression Score (Scaled to 0-5)
                dep_score = 0
                if tgds_val >= 10: dep_score = 3.75 + (tgds_val - 10) * 0.25
                elif tgds_val >= 5: dep_score = 2.0 + (tgds_val - 5) * 0.35
                
                final_display_score = max(clinical_dementia_score, sra_score, dep_score)
                final_display_score = round(min(5.0, final_display_score), 1)

                # Badge mapping
                badge_map = {"high": "rose", "medium": "amber", "low": "emerald"}
                
                # Risk Level Determination
                if final_display_score >= 3.75: f_lvl = "high"
                elif final_display_score >= 2.0: f_lvl = "medium"
                else: f_lvl = "low"
                
                risk_badge = badge_map.get(f_lvl, "emerald")

                # Mapping findings
                findings = []
                if prediction.get("state") == "Dementia": findings.append("ความเสี่ยงภาวะสมองเสื่อม")
                elif prediction.get("state") == "MCI": findings.append("ความเสี่ยงภาวะ MCI")
                if tgds_val >= 10: findings.append("ภาวะซึมเศร้ารุนแรง")
                elif tgds_val >= 5: findings.append("ภาวะซึมเศร้า")
                if sra_val >= 17: findings.append("ความเสี่ยงด้านความปลอดภัย")

                # Final labels
                if f_lvl == "high":
                    overall_label = "เสี่ยงสูง"
                elif f_lvl == "medium":
                    overall_label = "เสี่ยงปานกลาง"
                else:
                    overall_label = "ปกติ/เสี่ยงต่ำ"
                
                desc = f"ตรวจพบ: {', '.join(findings)}" if findings else "ไม่พบความเสี่ยงที่ผิดปกติ"

                # Progress percentages (based on 5.0 max)
                mmse_pct = int((clinical_dementia_score / 5) * 100)
                tgds_pct = int((dep_score / 5) * 100)
                sra_pct = int((sra_score / 5) * 100)
                
                ai_analysis = {
                    "overall_label": overall_label,
                    "overall_desc": desc,
                    "risk_score": final_display_score, 
                    "risk_max": 5,
                    "risk_badge": risk_badge,
                    "domains": [
                        {
                            "name": "สมรรถภาพสมอง (MMSE)", 
                            "percent": mmse_pct, 
                            "tone": "bad" if prediction.get("state") == "Dementia" else "warn" if prediction.get("state") == "MCI" else "good", 
                            "note": f"สถานะ: {prediction.get('state')}"
                        },
                        {
                            "name": "สภาวะทางอารมณ์ (TGDS)", 
                            "percent": tgds_pct, 
                            "tone": "bad" if tgds_val >= 10 else "warn" if tgds_val >= 5 else "good", 
                            "note": f"TGDS {int(tgds_val)}/15"
                        },
                        {
                            "name": "ความปลอดภัย/ฆ่าตัวตาย", 
                            "percent": sra_pct, 
                            "tone": "bad" if sra_val >= 17 else "warn" if sra_val >= 9 else "good", 
                            "note": "อิงจากการประเมิน SRA"
                        },
                        {
                            "name": "ความแม่นยำ (Confidence)", 
                            "percent": int(prediction.get("confidence") or 85), 
                            "tone": "good", 
                            "note": "ระดับความเชื่อมั่นของ AI"
                        },
                    ],
                    "cautions": [prediction.get("warning")] if prediction.get("warning") else [],
                    "recs": []
                }
                
                if prediction.get("state") == "Dementia":
                    ai_analysis["recs"].extend(["ควรตรวจประเมิน MoCA หรือ MRI เพิ่มเติม", "ทบทวนการใช้ยาที่มีผลต่อระบบประสาท"])
                elif prediction.get("state") == "MCI":
                    ai_analysis["recs"].append("แนะนำกิจกรรมลับสมองและเข้าสังคม")
                if sra_val >= 9:
                    ai_analysis["recs"].append("ควรส่งพบผู้เชี่ยวชาญด้านสุขภาพจิต")
                if not ai_analysis["recs"]:
                    ai_analysis["recs"].append("ติดตามอาการตามนัดหมายปกติ")
            else:
                raise Exception(prediction.get("error", "Unknown error"))
                
        except Exception as e:
            print(f"⚠️ AI Prediction failed: {e}")
            ai_analysis = {
                "overall_label": "รอการประเมิน",
                "overall_desc": "กรุณาประเมิน MMSE และ TGDS เพื่อให้ AI วิเคราะห์ผล",
                "risk_score": "-",
                "risk_badge": "gray",
                "domains": [],
                "cautions": [],
                "recs": [],
                "risk_level": "N/A",
            }


        # Safe latest_c
        latest_c = consultations_data[0] if consultations_data else {}
        
        # 7) Pull scores and general info from latest cga_record if available
        latest_cga = cga_history[0] if cga_history else {}

        # 8) Fetch detailed answers and scores if session_id exists
        mmse_details = {}
        tgds_details = {}
        q8_details = {}
        
        latest_session_id = latest_cga.get("session_id") or latest_c.get("session_id")
        print(f"DEBUG: patient_detail HN={hn} latest_session_id={latest_session_id}")
        
        if latest_session_id:
            try:
                # A) Detailed answers
                res_ans = supabase.table("assessment_answers").select("*").eq("session_id", latest_session_id).execute()
                print(f"DEBUG: Fetched {len(res_ans.data or [])} answers for session {latest_session_id}")
                for row in (res_ans.data or []):
                    inst = str(row.get("instrument") or "").lower()
                    q_no = row.get("question_no")
                    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")
                    
                    if inst == "mmse":
                        # Map to keys expected by mmse_form_partial.html
                        # e.g. q1_time_score, q2_place_score, etc.
                        if q_no == 1: mmse_details["q1_time_score"] = row.get("score")
                        elif q_no == 2: mmse_details["q2_place_score"] = row.get("score")
                        elif q_no == 3: mmse_details["q3_registration_score"] = row.get("score")
                        elif q_no == 4: mmse_details["q4_attention_calc_score"] = row.get("score")
                        elif q_no == 5: mmse_details["q5_recall_score"] = row.get("score")
                        elif q_no == 6: mmse_details["q6_naming_score"] = row.get("score")
                        elif q_no == 7: mmse_details["q7_repetition_score"] = row.get("score")
                        elif q_no == 8: mmse_details["q8_verbal_command_score"] = row.get("score")
                        elif q_no == 9: mmse_details["q9_written_command_score"] = row.get("score")
                        elif q_no == 10: mmse_details["q10_writing_score"] = row.get("score")
                        elif q_no == 11: mmse_details["q11_visuoconstruction_score"] = row.get("score")
                        
                        # Handle individual tags if they were saved in answer_text (like 'q1_1')
                        txt = str(row.get("answer_text") or "").lower()
                        if "_" in txt: 
                            mmse_details[txt] = row.get("score")
                            print(f"DEBUG: Mapped MMSE answer {txt}={row.get('score')}")
                    elif inst == "tgds":
                        tgds_details[f"tgds_{q_no}"] = "yes" if val in [1, "1", "yes"] else "no"
                    elif inst == "8q":
                        q8_details[f"q8_{q_no}"] = val
                        # Capture sub-question/remarks for Q3
                        if q_no == 3:
                            remarks = row.get("remarks")
                            if remarks:
                                q8_details["q3_sub"] = 1 if "cannot_control" in str(remarks).lower() else 0
                            # Try to find q3_sub if stored as a separate question_no or field
                            if row.get("answer_text") == "cannot_control":
                                q8_details["q3_sub"] = 1
                            elif row.get("answer_text") == "can_control":
                                q8_details["q3_sub"] = 0

                # B) Formal scores from assessment_scores table
                res_scores = supabase.table("assessment_scores").select("*").eq("session_id", latest_session_id).execute()
                for s in (res_scores.data or []):
                    inst = str(s.get("instrument") or "").lower()
                    if inst == "mmse":
                        mmse_details["score_total"] = s.get("total_score")
                        mmse_details["interpretation"] = s.get("risk_level") or s.get("interpretation")
                    elif inst == "tgds":
                        tgds_details["total_score"] = s.get("total_score")
                        tgds_details["interpretation"] = s.get("risk_level") or s.get("interpretation")
                    elif inst == "8q":
                        q8_details["total_score"] = s.get("total_score")
                        q8_details["risk_level"] = s.get("risk_level") or s.get("interpretation")

                # Fallback summary fields if assessment_scores was missing
                if "score_total" not in mmse_details:
                    mmse_details["score_total"] = latest_cga.get("mmse_score")
                    mmse_details["interpretation"] = latest_cga.get("mmse_result")
                if "total_score" not in tgds_details:
                    tgds_details["total_score"] = latest_cga.get("tgds_score")
                    tgds_details["interpretation"] = latest_cga.get("tgds_result")
                if "total_score" not in q8_details:
                    q8_details["total_score"] = latest_cga.get("q8_score") or latest_c.get("q8_score")
                    q8_details["risk_level"] = latest_cga.get("suicide_risk_level") or latest_c.get("suicide_risk_level")

            except Exception as e:
                print(f"DEBUG: Answers/Scores Fetch Error: {e}")

        # 9) Extract from health_behavior or nurse notes if exists (e.g. "smoke:none, alcohol:social")
        hb_combined = (str(latest_c.get("health_behavior") or "") + " " + str(latest_c.get("note_from_nurse") or "")).lower()
        ext_smoke = None
        ext_alcohol = None
        if "smoke:" in hb_combined:
            try: ext_smoke = hb_combined.split("smoke:")[1].split(",")[0].strip()
            except: pass
        if "alcohol:" in hb_combined:
            try: ext_alcohol = hb_combined.split("alcohol:")[1].split(",")[0].strip()
            except: pass
        
        # Helper to map smoking/alcohol values
        def _map_smoke(v):
            v = str(v or "").lower()
            if v in ['no', 'none', 'never', '0', 'ไม่สูบ']: return 'no'
            if v in ['yes', '1', 'สูบ']: return 'yes'
            if v in ['quit', 'เคยสูบ', 'เลิกแล้ว']: return 'quit'
            return v

        def _map_alcohol(v):
            v = str(v or "").lower()
            if v in ['never', 'none', 'no', '0', 'ไม่ดื่ม']: return 'never'
            if v in ['sometimes', 'social', 'บางครั้ง']: return 'sometimes'
            if v in ['daily', 'ทุกวัน']: return 'daily'
            return v

        def _clean_behavioral_tags(s):
            if not s or s == "-": return s
            s = re.sub(r'smoke:\s*[^,]+,?', '', s, flags=re.IGNORECASE)
            s = re.sub(r'alcohol:\s*[^,]+,?', '', s, flags=re.IGNORECASE)
            return s.strip().strip(",").strip() or "-"

        # 10) Final scores assembly (Merge details with summary scores)
        # Ensure MMSE/TGDS are mappings if we have at least summary info, to trigger form display
        # Fallback to consultations (latest_c) if cga_records (latest_cga) is missing data
        final_mmse = mmse_details
        mmse_score_val = latest_cga.get("mmse_score") if latest_cga.get("mmse_score") is not None else latest_c.get("mmse_score")
        
        if not final_mmse and mmse_score_val is not None:
            final_mmse = {
                "score_total": mmse_score_val,
                "interpretation": latest_cga.get("mmse_result") or latest_c.get("cognition_status") or "-",
                "education_level": latest_cga.get("education") or "-",
                "is_summary_only": True
            }
        elif final_mmse:
            final_mmse["score_total"] = mmse_score_val
            final_mmse["interpretation"] = latest_cga.get("mmse_result") or latest_c.get("cognition_status") or "-"
            final_mmse["education_level"] = latest_cga.get("education") or "-"

        final_tgds = tgds_details
        tgds_score_val = latest_cga.get("tgds_score") if latest_cga.get("tgds_score") is not None else latest_c.get("tgds_score")
        
        if not final_tgds and tgds_score_val is not None:
            final_tgds = {
                "total_score": tgds_score_val,
                "interpretation": latest_cga.get("tgds_result") or "-",
                "is_summary_only": True
            }
        elif final_tgds:
            final_tgds["total_score"] = tgds_score_val
            final_tgds["interpretation"] = latest_cga.get("tgds_result") or "-"

        # Parse 2Q from string (Fallback from consultations)
        final_twoq = latest_c.get("depression_2q")
        if isinstance(final_twoq, str) and "q1:" in final_twoq.lower():
            try:
                parts = final_twoq.lower().split(",")
                q1_val = parts[0].split(":")[1].strip() if ":" in parts[0] else "no"
                q2_val = parts[1].split(":")[1].strip() if ":" in parts[1] else "no"
                final_twoq = {"q1": q1_val, "q2": q2_val, "yes_count": (1 if q1_val == "yes" else 0) + (1 if q2_val == "yes" else 0)}
            except: pass

        # Force 8Q mapping using 'suicide_risk' from cga_records
        final_8q = q8_details
        q8_val_raw = latest_cga.get("suicide_risk")
        
        if not final_8q and q8_val_raw:
            # Determine score if it's a string like 'มี' or 'yes'
            calc_score = 0
            if str(q8_val_raw).lower() in ['มี', 'yes', 'true']: calc_score = 17
            else:
                try: calc_score = int(float(q8_val_raw))
                except: calc_score = 0

            final_8q = {
                "total_score": calc_score,
                "risk_level": q8_val_raw,
                "is_summary_only": True
            }
        elif final_8q:
            final_8q["risk_level"] = q8_val_raw

        scores = {
            "mmse": final_mmse, 
            "tgds": final_tgds, 
            "sra": 0, 
            "twoq": final_twoq,
            "8q": final_8q
        }
        
        # General info: prefer latest_cga, then latest_c
        cga_general = {
            "caregiver_name": latest_cga.get("caregiver_name") or latest_c.get("caregiver_name") or "-", 
            "caregiver_phone": latest_cga.get("phone") or latest_c.get("caregiver_phone") or "-",
            "caregiver_relation": latest_c.get("caregiver_relation") or "-",
            "disease": latest_cga.get("comorbidity_detail") or latest_c.get("note_from_nurse"),
            "smoking_status": latest_cga.get("smoke") or latest_c.get("smoke"),
            "alcohol_level": latest_cga.get("alcohol") or latest_c.get("alcohol"),
            "sleep_problem": latest_cga.get("sleep_problem"),
            "urinary_incontinence": latest_cga.get("incontinence"),
            "height": latest_cga.get("height"),
            "waist": latest_cga.get("waist"),
            "hearing_left": latest_cga.get("hearing_left_result"),
            "hearing_right": latest_cga.get("hearing_right_result"),
            "vision_left": latest_cga.get("vision_left_snellen"),
            "vision_right": latest_cga.get("vision_right_snellen"),
            "addr_no": latest_cga.get("house_no"),
            "moo": latest_cga.get("moo"),
            "subdistrict": latest_cga.get("subdistrict"),
            "district": latest_cga.get("district"),
            "province": latest_cga.get("province"),
        }

        return render_template(
            "doctor/medical_patients_detail.html",
            patients=patient,
            cga_general=cga_general,
            scores=scores,
            visits=visits,
            upcoming_appts=upcoming_appts,
            ai_analysis=ai_analysis,
            encounter_id=encounter_id,
            consultations=consultations_data,
            cga_history=cga_history,
            mmse=final_mmse,
            tgds=final_tgds,
            twoq=final_twoq,
            q8=final_8q
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Patient Detail Error: {e}")
        flash("เกิดข้อผิดพลาดในการโหลดข้อมูล", "error")
        return redirect(url_for("doctor.patients"))


@doctor_bp.post("/patient/<hn>/visit/create", endpoint="visit_create")
def visit_create(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    chief = (request.form.get("chief_complaint") or "").strip()
    diagnosis = (request.form.get("diagnosis") or "").strip()
    plan = (request.form.get("treatment_plan") or "").strip()
    
    encounter_type = (request.form.get("encounter_type") or "cga").strip().lower()
    doctor_id = session.get("user_id")

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        res_p = supabase.table("patients").select("id").eq("hn", hn).limit(1).execute()
        if not res_p.data:
            flash("ไม่พบผู้ป่วย", "error")
            return redirect(url_for("doctor.patients"))
        
        patient_id = res_p.data[0]["id"]
        
        # 1) Create/Get Encounter
        # We'll create a new encounter for this recording
        enc_data = {
            "patient_id": patient_id,
            "encounter_date": date.today().isoformat(),
            "encounter_type": encounter_type,
            "created_by": doctor_id,
            "note": f"CC: {chief}" # Store Subjective in encounter note
        }
        res_enc = supabase.table("encounters").insert(enc_data).execute()
        if not res_enc.data:
            raise Exception("Failed to create encounter")
        
        encounter_id = res_enc.data[0]["id"]

        # 2) Create Doctor Note (A & P)
        note_data = {
            "encounter_id": encounter_id,
            "doctor_id": doctor_id,
            "diagnosis": diagnosis,
            "plan": plan
        }
        supabase.table("doctor_notes").insert(note_data).execute()
        
        flash("บันทึกการวินิจฉัยเรียบร้อยแล้ว", "success")
    except Exception as e:
        print(f"Error in visit_create: {e}")
        flash(f"บันทึกไม่สำเร็จ: {e}", "error")

    return redirect(url_for("doctor.patient_detail", hn=hn))


@doctor_bp.post("/patient/<hn>/appointment/create", endpoint="appointment_create")
def appointment_create(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    appt_dt_str = (request.form.get("appt_datetime") or "").strip()
    appt_type = (request.form.get("appt_type") or "followup").strip()
    note = (request.form.get("note") or "").strip()
    location = (request.form.get("location") or "ชั้น 2 คลินิกผู้สูงอายุ").strip()
    doctor_id = session.get("user_id")

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        res_p = supabase.table("patients").select("id").eq("hn", hn).limit(1).execute()
        if not res_p.data:
            flash("ไม่พบผู้ป่วย", "error")
            return redirect(url_for("doctor.patients"))
        
        patient_id = res_p.data[0]["id"]
        
        try:
            dt = datetime.strptime(appt_dt_str, "%Y-%m-%d %H:%M:%S")
            iso_dt = dt.isoformat()
        except:
            iso_dt = appt_dt_str

        data = {
            "patient_id": patient_id,
            "created_by_doctor": doctor_id,
            "appt_datetime": iso_dt,
            "appt_type": appt_type,
            "status": "scheduled",
            "note": f"{location} | {note}".strip() if note else location
        }
        supabase.table("appointments").insert(data).execute()
        
        try:
            if line_bot_api:
                p_res = supabase.table("patients").select("line_user_id, full_name").eq("id", patient_id).single().execute()
                if p_res.data and p_res.data.get("line_user_id"):
                    line_id = p_res.data["line_user_id"]
                    p_name = p_res.data["full_name"]
                    dt_parsed = datetime.fromisoformat(iso_dt.replace('Z', '+00:00'))
                    th_date = dt_parsed.strftime('%d/%m/') + str(dt_parsed.year + 543)
                    th_time = dt_parsed.strftime('%H:%M')
                    
                    msg = (
                        f"✅ ยืนยันการนัดหมาย\n"
                        f"คุณ {p_name}\n"
                        f"นัด: {appt_type}\n"
                        f"วันที่: {th_date} เวลา {th_time} น.\n"
                        f"ระบบจะแจ้งเตือนอีกครั้งก่อนถึงวันนัด 1 วันค่ะ"
                    )
                    line_bot_api.push_message(line_id, TextSendMessage(text=msg))
        except Exception as line_err:
            print(f"Line Error: {line_err}")

        flash("เพิ่มนัดหมายเรียบร้อย", "success")
    except Exception as e:
        flash(f"บันทึกนัดหมายไม่สำเร็จ: {e}", "error")

    return redirect(url_for("doctor.patient_detail", hn=hn))


# ==============================
# PATIENT DELETE
# ==============================
@doctor_bp.get("/patients/<hn>/delete", endpoint="patients_delete_get")
def patients_delete_get(hn):
    return redirect(url_for("doctor.patients"))


@doctor_bp.get("/patient/<hn>/consultations", endpoint="patient_consultations")
def patient_consultations(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("doctor.patients"))

    try:
        # 1) ดึงข้อมูลผู้ป่วย
        res_p = supabase.table("patients").select("*").eq("hn", hn).single().execute()
        patient = res_p.data
        if not patient:
            flash("ไม่พบข้อมูลผู้ป่วย", "error")
            return redirect(url_for("doctor.patients"))

        # 2) ดึงข้อมูลจาก doctor_notes (ทำหน้าที่เป็น consultations)
        # เนื่องจาก doctor_notes ผูกกับ encounters, และ encounters ผูกกับ patient
        # เราต้องหา encounter_id ของคนไข้ก่อน หรือ join (Supabase join: doctor_notes(*, encounters!inner(*)))
        
        res_notes = supabase.table("doctor_notes") \
            .select("*, encounters!inner(patient_id, encounter_date), users(full_name)") \
            .eq("encounters.patient_id", patient["id"]) \
            .order("created_at", desc=True) \
            .execute()
            
        consultations = []
        for n in (res_notes.data or []):
            # Map fields to what the template expects
            doc = n.get("users") or {}
            doc_name = doc.get("full_name") or "แพทย์ผู้ตรวจ"
            
            enc = n.get("encounters") or {}
            enc_date = enc.get("encounter_date")
            
            created_at = n.get("created_at")
            
            # Date Display
            date_display = "-"
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    date_display = dt.strftime("%d/%m/%Y %H:%M")
                except:
                    date_display = str(created_at)
            elif enc_date:
                try:
                    dt = datetime.strptime(enc_date, "%Y-%m-%d")
                    date_display = dt.strftime("%d/%m/%Y")
                except:
                    date_display = enc_date

            consultations.append({
                "date_display": date_display,
                "topic": "บันทึกการตรวจรักษา (Doctor Note)",
                "consultant_name": doc_name,
                "details": n.get("diagnosis") or "-",
                "recommendations": n.get("plan") or "-",
                "diagnosis": n.get("diagnosis"),
                "status": "completed"
            })

        return render_template("doctor/medical_consultations.html", patient=patient, consultations=consultations)
    except Exception as e:
        print(f"❌ Consultations Error: {e}")
        flash(f"เกิดข้อผิดพลาดในการดึงข้อมูลคำปรึกษา: {e}", "error")
        return redirect(url_for("doctor.patients"))


@doctor_bp.post("/patients/<hn>/delete", endpoint="patients_delete")
def patients_delete(hn):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        supabase.table("patients").delete().eq("hn", hn).execute()
        flash("ลบข้อมูลผู้ป่วยเรียบร้อย", "success")
    except Exception as e:
        flash(f"ลบไม่สำเร็จ: {e}", "error")

    return redirect(url_for("doctor.patients"))


@doctor_bp.get("/encounter/<int:encounter_id>", endpoint="encounter_detail")
def encounter_detail(encounter_id):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        # Use .execute() instead of .single() to prevent crash if record is missing
        res_e = supabase.table("encounters") \
            .select("*, patients(id, hn, full_name), users!encounters_created_by_fkey(full_name)") \
            .eq("id", encounter_id).execute()
        
        if not res_e.data:
            flash("ไม่พบรายการตรวจ", "error")
            return redirect(url_for("doctor.patients"))
        
        enc = res_e.data[0]
        
        p_data = enc.get("patients") or {}
        enc["hn"] = p_data.get("hn")
        enc["full_name"] = p_data.get("full_name")
        
        # Add creator name for the template
        u_data = enc.get("users!encounters_created_by_fkey") or {}
        enc["creator_name"] = u_data.get("full_name") or "ไม่ระบุชื่อ"
        
        if enc.get("created_at"):
            enc["created_at"] = _parse_iso(enc["created_at"])

        # Fetch clinical data from cga_records
        # Use patient_id to get the most recent data available for this person
        cga_info = {}
        try:
            # Get latest clinical info for this patient across all their encounters
            res_cga = supabase.table("cga_records") \
                .select("*") \
                .eq("patient_id", enc["patient_id"]) \
                .order("assessed_date", desc=True) \
                .limit(1).execute()

            if res_cga.data:
                raw_cga = res_cga.data[0]
                
                # Map smoking
                smoke_raw = str(raw_cga.get("smoke") or "").lower()
                smoke_th = "ไม่สูบ"
                if smoke_raw in ['yes', 'สูบ', '1']: smoke_th = "สูบ"
                elif smoke_raw in ['quit', 'เลิกแล้ว', 'เลิกสูบ']: smoke_th = "เลิกแล้ว"
                elif smoke_raw == "": smoke_th = "-"

                # Map alcohol
                alc_raw = str(raw_cga.get("alcohol") or "").lower()
                alc_th = "ไม่เคยดื่ม"
                if alc_raw in ['daily', 'ทุกวัน', 'ดื่มทุกวัน']: alc_th = "ดื่มทุกวัน"
                elif alc_raw in ['social', 'sometimes', 'บางครั้ง', 'ดื่มบางครั้ง']: alc_th = "ดื่มบางครั้ง"
                elif alc_raw == "": alc_th = "-"

                # Map Caregiver
                cg_name = raw_cga.get("caregiver_name") or "-"
                cg_rel = raw_cga.get("caregiver_relation")
                if cg_rel and cg_name != "-":
                    cg_display = f"{cg_name} ({cg_rel})"
                else:
                    cg_display = cg_name

                cga_info = {
                    "height": raw_cga.get("height") or "-",
                    "waist": raw_cga.get("waist") or "-",
                    "smoke": smoke_th,
                    "alcohol": alc_th,
                    "caregiver_name": cg_display,
                    "vision_left": raw_cga.get("vision_left") or "-",
                    "vision_right": raw_cga.get("vision_right") or "-",
                    "hearing_left": raw_cga.get("hearing_left") or "-",
                    "hearing_right": raw_cga.get("hearing_right") or "-",
                    "mmse_score": raw_cga.get("mmse_score"),
                    "tgds_score": raw_cga.get("tgds_score"),
                    "suicide_risk": raw_cga.get("suicide_risk") or "-"
                }
        except Exception as e:
            print(f"⚠️ Error fetching latest clinical info for patient: {e}")

        res_n = supabase.table("doctor_notes") \
            .select("*, users(full_name)") \
            .eq("encounter_id", encounter_id)\
            .order("created_at", desc=True).execute()
        dx_notes = res_n.data or []
        for n in dx_notes:
            if n.get("created_at"):
                n["created_at"] = _parse_iso(n["created_at"])

        scores_data = {}
        try:
            res_sess = supabase.table("assessment_sessions").select("id").eq("encounter_id", encounter_id).execute()
            sess_ids = [s["id"] for s in (res_sess.data or [])]
            if sess_ids:
                res_scores = supabase.table("assessment_scores").select("*").in_("session_id", sess_ids).execute()
                for s in (res_scores.data or []):
                    scores_data[s["instrument"].lower()] = s
        except Exception as e:
            print(f"⚠️ Error fetching scores: {e}")

        return render_template(
            "doctor/medical_encounter_detail.html",
            enc=enc,
            cga_info=cga_info,
            dx_notes=dx_notes,
            scores=scores_data.values(),
            mmse=scores_data.get("mmse"),
            tgds=scores_data.get("tgds"),
            twoq=scores_data.get("2q"),
            q8=scores_data.get("8q")
        )
    except Exception as e:
        print(f"❌ Encounter Detail Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        return redirect(url_for("doctor.patients"))


@doctor_bp.get("/patient/summary/<int:id>", endpoint="patient_summary")
def patient_summary(id):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        # 1) Try to find by encounter_id first, fallback to cga_records id
        # We'll first try to fetch from cga_records to get the basic info and potential encounter_id
        res_cga = supabase.table("cga_records").select("*, patients(*)").eq("id", id).execute()
        
        # If not found by ID, maybe the passed ID IS an encounter_id? 
        # Let's try to find in cga_records where encounter_id = id
        if not res_cga.data:
            res_cga = supabase.table("cga_records").select("*, patients(*)").eq("encounter_id", id).execute()
        
        if not res_cga.data:
            flash("ไม่พบข้อมูลการประเมิน", "error")
            return redirect(url_for("doctor.reports"))
            
        cga_data = res_cga.data[0]
        encounter_id = cga_data.get("encounter_id")
        patient = cga_data.get("patients") or {}
        
        # Fallback for patient info if not joined correctly
        if not patient and cga_data.get("patient_id"):
            res_p = supabase.table("patients").select("*").eq("id", cga_data["patient_id"]).single().execute()
            patient = res_p.data or {}

        # Ensure birth_date is a date object for template calculation
        if patient.get("birth_date") and isinstance(patient["birth_date"], str):
            try:
                patient["birth_date"] = datetime.strptime(patient["birth_date"][:10], "%Y-%m-%d").date()
            except: pass

        # Fallback gender detection from prefix or name
        if not patient.get("gender"):
            # Check prefix column first
            pref = str(patient.get("prefix") or "").strip()
            if pref in ["นาย"]: patient["gender"] = "ชาย"
            elif pref in ["นาง", "นางสาว", "น.ส."]: patient["gender"] = "หญิง"
            # Then check name
            if not patient.get("gender") and patient.get("full_name"):
                patient["gender"] = _detect_gender(patient["full_name"])

        # 2) Get Scores (Try from assessment_scores if encounter_id exists)
        mmse_val = cga_data.get("mmse_score")
        mmse_flag = cga_data.get("mmse_result")
        tgds_val = cga_data.get("tgds_score")
        tgds_flag = cga_data.get("tgds_result")
        sra_val = 0
        sra_flag = cga_data.get("suicide_risk_level") or cga_data.get("suicide_risk")

        try:
            s_raw = cga_data.get("q8_score") or cga_data.get("sra_score") or cga_data.get("suicide_risk") or 0
            if s_raw:
                if str(s_raw).lower() in ['มี', 'yes', 'true']: sra_val = 17
                elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']: sra_val = 0
                else: sra_val = int(float(s_raw))
        except: pass

        # 3) Diagnosis Notes (Fetch ALL history for this patient)
        dx_notes = []
        patient_id = patient.get("id")
        if patient_id:
            # Join with encounters to filter by patient_id
            res_notes = supabase.table("doctor_notes") \
                .select("*, users(full_name), encounters!inner(patient_id)") \
                .eq("encounters.patient_id", patient_id) \
                .order("created_at", desc=True).execute()
            
            if res_notes.data:
                for n in res_notes.data:
                    doc_name = n.get("users", {}).get("full_name") or "แพทย์ผู้ตรวจ"
                    dt_obj = _parse_iso(n.get("created_at"))
                    date_str = dt_obj.strftime("%d/%m/%Y %H:%M") if dt_obj else "-"
                    
                    dx_notes.append({
                        "diagnosis": n.get("diagnosis"),
                        "plan": n.get("plan"),
                        "doctor": doc_name,
                        "date": date_str,
                        "note": f"Diagnosis: {n.get('diagnosis')}\nPlan: {n.get('plan')}"
                    })

        return render_template(
            "doctor/medical_patient_summary.html",
            patients=patient,
            cga_data=cga_data,
            mmse=mmse_val,
            mmse_flag=mmse_flag,
            tgds=tgds_val,
            tgds_flag=tgds_flag,
            sra=sra_val,
            sra_flag=sra_flag,
            notes=dx_notes,
            last_date=cga_data.get("assessed_date") or cga_data.get("created_at"),
            now_year=date.today().year
        )
    except Exception as e:
        print(f"❌ Patient Summary Error: {e}")
        flash(f"เกิดข้อผิดพลาด: {e}", "error")
        return redirect(url_for("doctor.reports"))


# ==============================
# DUTY
# ==============================
@doctor_bp.get("/duty")
def duty():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    return render_template("doctor/medical_doctorduty.html")


@doctor_bp.get("/duty/events", endpoint="doctor_duty_events")
def doctor_duty_events():
    if not _guard_doctor():
        return jsonify([]), 401

    doctor_id = session.get("user_id")
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        res = supabase.table("doctor_duty_events").select("id, title, note, start_datetime, end_datetime")\
            .eq("doctor_id", doctor_id).order("start_datetime").execute()
        rows = res.data or []
        events = []
        for r in rows:
            events.append({
                "id": r["id"],
                "title": r["title"] or "ตารางเข้าเวร",
                "start": r["start_datetime"],
                "end": r["end_datetime"],
                "extendedProps": {
                    "shift_type": r["title"],
                    "note": r["note"] or "",
                }
            })
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@doctor_bp.post("/duty/create", endpoint="doctor_duty_create")
def doctor_duty_create():
    if not _guard_doctor():
        return jsonify({"ok": False, "message": "unauthorized"}), 401

    doctor_id = session.get("user_id")
    data = request.get_json(silent=True) if request.is_json else (request.form.to_dict(flat=True) or {})
    data = data or {}

    def pick(*keys, default=""):
        for k in keys:
            v = data.get(k)
            if v is not None:
                if isinstance(v, str):
                    v = v.strip()
                    if v != "": return v
                else: return v
        return default

    date_raw = pick("shift_date", "date", "selected_date")
    start_time = pick("start_time", "startTime")
    end_time = pick("end_time", "endTime")
    shift = pick("shift_type", "shift", "title", default="Day")
    note = pick("location", "note")

    def parse_iso(dt_str: str):
        if not dt_str: return None
        try:
            s = dt_str.strip()
            if s.endswith("Z"): s = s[:-1]
            if "+" in s: s = s.split("+", 1)[0]
            if s.count(":") == 1 and "T" in s: s = s + ":00"
            return datetime.fromisoformat(s)
        except: return None

    start_dt = parse_iso(pick("start_datetime", "start"))
    end_dt = parse_iso(pick("end_datetime", "end"))

    if not start_dt:
        if not date_raw or not start_time:
            return jsonify({"ok": False, "message": "missing required fields"}), 400
        try:
            start_dt = datetime.fromisoformat(f"{date_raw} {start_time}:00")
        except:
            return jsonify({"ok": False, "message": "bad date/start_time"}), 400

    if not end_dt:
        if end_time and date_raw:
            try: end_dt = datetime.fromisoformat(f"{date_raw} {end_time}:00")
            except: end_dt = None
        if not end_dt: end_dt = start_dt

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        data_ins = {
            "doctor_id": doctor_id,
            "title": shift,
            "note": note if note else None,
            "start_datetime": start_dt.isoformat(),
            "end_datetime": end_dt.isoformat()
        }
        res = supabase.table("doctor_duty_events").insert(data_ins).execute()
        if res.data: return jsonify({"ok": True, "id": res.data[0]["id"]})
        return jsonify({"ok": False, "msg": "insert failed"}), 500
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@doctor_bp.post("/duty/delete", endpoint="doctor_duty_delete")
def doctor_duty_delete():
    if not _guard_doctor():
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    doctor_id = session.get("user_id")
    shift_id = (request.form.get("shift_id") or "").strip()
    if not shift_id.isdigit():
        return jsonify({"ok": False, "msg": "shift_id ไม่ถูกต้อง"}), 400

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        supabase.table("doctor_duty_events").delete()\
            .eq("id", int(shift_id)).eq("doctor_id", int(doctor_id)).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@doctor_bp.post("/duty/note/save", endpoint="doctor_duty_note_save")
def doctor_duty_note_save():
    if not _guard_doctor():
        return jsonify({"ok": False, "msg": "unauthorized"}), 401

    doctor_id = session.get("user_id")
    shift_id = (request.form.get("shift_id") or "").strip()
    note = (request.form.get("note") or "").strip()
    if not shift_id.isdigit():
        return jsonify({"ok": False, "msg": "shift_id ไม่ถูกต้อง"}), 400

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        supabase.table("doctor_duty_events").update({"note": note})\
            .eq("id", int(shift_id)).eq("doctor_id", int(doctor_id)).execute()
        return jsonify({"ok": True, "note": note})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


# ==============================
# REPORTS / ASSESSMENTS
# ==============================
@doctor_bp.get("/reports")
def reports():
    if not _guard_doctor():
        return redirect(url_for("auth.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("auth.login"))

    try:
        # Get HN/Name filters from query
        hn_q = (request.args.get("hn") or "").strip()
        name_q = (request.args.get("name") or "").strip()
        risk_q = (request.args.get("risk") or "").strip()

        # 1) Fetch data from cga_records (Source of Truth for Nurse Assessments)
        query = supabase.table("cga_records").select("*, patients(*)")
        
        if hn_q:
            query = query.ilike("hn", f"%{hn_q}%")
        # Note: Name filtering might need complex query if searching through joined table, 
        # but usually cga_records has patient info or we can filter after fetch for simplicity in this case.
        
        res_assess = query.order("id", desc=True).execute()
        raw_data = res_assess.data or []

        processed_reports = []
        today = date.today()

        for r in raw_data:
            p = r.get("patients") or {}
            full_name = (p.get("full_name") or r.get("full_name") or "ไม่ระบุชื่อ").strip()
            hn = p.get("hn") or r.get("hn") or "-"
            
            # Filter by name if provided
            if name_q and name_q.lower() not in full_name.lower():
                continue

            # Calculate Age
            bd_str = p.get("birth_date") or p.get("dob")
            age = r.get("age") or "-"
            if not age or age == "-":
                if bd_str:
                    try:
                        bd = datetime.strptime(bd_str[:10], "%Y-%m-%d").date()
                        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                    except: pass

            # Risk Level Logic (Refined)
            m_score = r.get("mmse_score")
            t_score = r.get("tgds_score")
            
            sra = 0
            try:
                s_raw = r.get("q8_score") or r.get("sra_score") or r.get("suicide_risk") or 0
                if s_raw:
                    if str(s_raw).lower() in ['มี', 'yes', 'true']:
                        sra = 17
                    elif str(s_raw).lower() in ['ไม่มี', 'no', 'none', 'false']:
                        sra = 0
                    else:
                        sra = int(float(s_raw))
            except:
                sra = 0
            
            risk_label = "ปกติ"
            risk_slug = "low"
            if sra >= 17 or (t_score is not None and t_score >= 6) or (m_score is not None and m_score <= 21):
                risk_label = "สูง"
                risk_slug = "high"
            elif sra >= 9 or (t_score is not None and t_score >= 4) or (m_score is not None and m_score <= 25):
                risk_label = "ปานกลาง"
                risk_slug = "medium"

            # Filter by risk if provided
            if risk_q and risk_q != risk_label:
                continue

            # Date Formatting
            d_str = r.get("assessed_date") or r.get("created_at")
            d_obj = None
            if d_str:
                try:
                    if 'T' in d_str: d_obj = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
                    else: d_obj = datetime.strptime(d_str[:10], "%Y-%m-%d")
                except: pass

            processed_reports.append({
                "id": r.get("id"),
                "hn": hn,
                "full_name": full_name,
                "patient_initials": full_name[0] if full_name and full_name != "ไม่ระบุชื่อ" else "ผ",
                "age": age,
                "date_th": format_thai_short_with_year(d_obj) if d_obj else "-",
                "mmse_score": m_score if m_score is not None else "-",
                "tgds_score": t_score if t_score is not None else "-",
                "risk": risk_label,
                "risk_slug": risk_slug
            })

        # Separate into Latest Assessments (top 5) and all filtered reports
        latest_assessments = processed_reports[:5]

        return render_template(
            "doctor/medical_reports.html",
            reports=processed_reports,
            latest_assessments=latest_assessments,
            hn_q=hn_q,
            name_q=name_q,
            risk=risk_q
        )

    except Exception as e:
        print("❌ Reports Error:", e)
        flash("เกิดข้อผิดพลาดในการโหลดรายงาน", "error")
        return redirect(url_for("doctor.dashboard"))


# ==============================
# CREATE REPORT
# ==============================
@doctor_bp.get("/reports/create")
def reports_create():
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))
    
    hn_q = (request.args.get("hn") or "").strip()
    name_q = (request.args.get("name") or "").strip()
    
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    if not supabase:
        flash("เชื่อมต่อ Supabase ไม่สำเร็จ", "error")
        return redirect(url_for("doctor.dashboard"))

    patients_list = []
    latest_assessments = []

    try:
        if hn_q or name_q:
            query = supabase.table("patients").select("*")
            if hn_q:
                query = query.ilike("hn", f"%{hn_q}%")
            if name_q:
                query = query.ilike("full_name", f"%{name_q}%")
            res = query.limit(20).execute()
            patients_list = res.data or []
        else:
            res_latest_e = supabase.table("encounters").select("*").order("created_at", desc=True).limit(5).execute()
            latest_e = res_latest_e.data or []
            
            p_ids = list(set(e['patient_id'] for e in latest_e if e.get('patient_id')))
            p_map = {}
            if p_ids:
                res_p = supabase.table("patients").select("id, hn, full_name, gender, birth_date").in_("id", p_ids).execute()
                p_map = {p_item['id']: p_item for p_item in (res_p.data or [])}

            today = date.today()
            for r in latest_e:
                p = p_map.get(r.get("patient_id")) or {}
                bd_str = p.get("birth_date")
                age = "-"
                if bd_str:
                    try:
                        bd = datetime.strptime(bd_str[:10], "%Y-%m-%d").date()
                        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                    except: pass
                
                p_name = (p.get("full_name") or "ไม่ระบุชื่อ").strip()
                latest_assessments.append({
                    "id": r["id"],
                    "hn": p.get("hn") or "-",
                    "full_name": p_name,
                    "gender": p.get("gender") or "-",
                    "age": age,
                    "date_th": format_thai_short_with_year(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).date()) if r.get("created_at") else "-"
                })

    except Exception as e:
        print(f"❌ Search/Latest Error: {e}")
        flash("เกิดข้อผิดพลาดในการดึงข้อมูล", "error")

    return render_template(
        "doctor/medical_report_create.html", 
        patients=patients_list, 
        latest_assessments=latest_assessments,
        hn_q=hn_q, 
        name_q=name_q
    )


@doctor_bp.get("/assessments", endpoint="doctor_assessments")
def assessments():
    if not _guard_doctor(): return redirect(url_for("doctor.login"))
    return redirect(url_for("doctor.patients"))


@doctor_bp.route("/encounter/<int:encounter_id>/diagnosis", methods=["GET", "POST"])
def diagnosis_notes(encounter_id):
    if not session.get("user_id"): return redirect(url_for("doctor.login"))
    doctor_id = session.get("user_id")
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()

    if request.method == "POST":
        data = {
            "encounter_id": encounter_id,
            "doctor_id": doctor_id,
            "diagnosis": request.form.get("diagnosis", "").strip(),
            "plan": request.form.get("plan", "").strip(),
            "followup_note": request.form.get("followup_note", "").strip()
        }
        supabase.table("doctor_notes").insert(data).execute()
        return redirect(url_for("doctor.diagnosis_notes", encounter_id=encounter_id))

    res = supabase.table("doctor_notes").select("*").eq("encounter_id", encounter_id).order("created_at", desc=True).execute()
    return render_template("doctor/medical_diagnosis.html", encounter_id=encounter_id, notes=res.data or [])


@doctor_bp.get("/appointment/<int:appt_id>", endpoint="appointment_detail")
def appointment_detail(appt_id):
    if not _guard_doctor(): return redirect(url_for("doctor.login"))
    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()
    try:
        # Simple join with users since only one relationship exists
        res = supabase.table("appointments") \
            .select("*, patients(hn, full_name, phone), users(full_name, username)") \
            .eq("id", appt_id).limit(1).execute()
            
        if not res.data: return redirect(url_for("doctor.patients"))
        appt = res.data[0]
        
        # Mapping for template
        p = appt.get("patients") or {}
        appt["hn"] = p.get("hn")
        appt["full_name"] = p.get("full_name")
        appt["patient_phone"] = p.get("phone")
        
        # User can be under 'users' (dict) or nothing
        u = appt.get("users") or {}
        # Use username as fallback if full_name is not set
        appt["doctor_name"] = u.get("full_name") or u.get("username") or "ไม่ระบุชื่อ"
        
        if appt.get("appt_datetime"):
            appt["appt_datetime"] = _parse_iso(appt["appt_datetime"])
            
        return render_template("doctor/medical_appointment_detail.html", appt=appt)
    except Exception as e:
        print(f"❌ Appointment Detail Error: {e}")
        return redirect(url_for("doctor.patients"))
    
    
    
@doctor_bp.get("/cga/<int:cga_id>", endpoint="cga_history_detail")
def cga_history_detail(cga_id):
    if not _guard_doctor():
        return redirect(url_for("doctor.login"))

    from db.db import get_db_client, get_db_connection
    supabase = get_db_client()

    try:
        # 1) Fetch main cga_record
        res_cga = supabase.table("cga_records") \
            .select("*, patients!cga_records_patient_id_fkey(*)") \
            .eq("id", cga_id).execute()
            
        if not res_cga.data:
            flash("ไม่พบข้อมูลการประเมิน", "error")
            return redirect(url_for("doctor.dashboard"))
            
        cga = res_cga.data[0]
        patient = cga.get("patients") or {}
        session_id = cga.get("session_id")
        
        # Ensure session_id is available (fallback to cga_headers)
        if not session_id and cga.get("encounter_id"):
            res_hdr = supabase.table("cga_headers").select("session_id").eq("encounter_id", cga["encounter_id"]).limit(1).execute()
            if res_hdr.data:
                session_id = res_hdr.data[0]["session_id"]

        # 2) Fetch detailed answers if session exists
        mmse_details = {}
        tgds_details = {}
        q8_details = {}
        twoq_details = {}
        
        if session_id:
            res_ans = supabase.table("assessment_answers").select("*").eq("session_id", session_id).execute()
            for row in (res_ans.data or []):
                inst = str(row.get("instrument") or "").lower()
                q_no = row.get("question_no")
                score = row.get("score")
                txt = str(row.get("answer_text") or "").lower()
                ans_int = row.get("answer_int")
                
                if inst == "mmse":
                    # Mapping standard MMSE keys
                    if q_no == 1: mmse_details["q1_time_score"] = score
                    elif q_no == 2: mmse_details["q2_place_score"] = score
                    # Map individual checkmarks (q1_1, q1_2, etc.)
                    if "_" in txt: mmse_details[txt] = score
                elif inst == "tgds":
                    tgds_details[f"tgds_{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"
                elif inst == "8q" or inst == "sra":
                    q8_details[f"q8_{q_no}"] = ans_int or txt
                elif inst == "2q":
                    twoq_details[f"q{q_no}"] = "yes" if (ans_int == 1 or txt == "yes") else "no"

        # 3) Prepare Score Objects for Template
        mmse_obj = mmse_details
        mmse_obj.update({
            "score_total": cga.get("mmse_score"),
            "interpretation": cga.get("mmse_result"),
            "education_level": cga.get("education"),
            "is_summary_only": not any("_" in k for k in mmse_details.keys()) # Check if detailed marks exist
        })

        tgds_obj = tgds_details
        tgds_obj.update({
            "total_score": cga.get("tgds_score"),
            "interpretation": cga.get("tgds_result"),
            "is_summary_only": not bool(tgds_details)
        })

        q8_obj = q8_details
        q8_obj.update({
            "total_score": cga.get("q8_score") or 0,
            "risk_level": cga.get("suicide_risk"),
            "is_summary_only": not bool(q8_details)
        })

        return render_template(
            "doctor/medical_cga_history_detail.html",
            cga=cga,
            patient=patient,
            mmse=mmse_obj,
            tgds=tgds_obj,
            q8=q8_obj,
            twoq=twoq_details
        )

    except Exception as e:
        print("❌ CGA History Detail Error:", e)
        flash("เกิดข้อผิดพลาดในการโหลดข้อมูลรายละเอียด", "error")
        return redirect(url_for("doctor.dashboard"))
    
@doctor_bp.route("/cga/<int:cga_id>")
@login_required
def cga_detail(cga_id):
    cga = CGA.query.get_or_404(cga_id)
    patient = cga.patient

    return render_template(
        "doctor/medical_cga_detail.html",
        cga=cga,
        patient=patient
    )
