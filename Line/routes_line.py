import os
from flask import Blueprint, render_template, jsonify, request
from db.db import get_db_client

line_bp = Blueprint("line", __name__, url_prefix="/line")

# --------- หน้า LIFF ---------
@line_bp.route("/liff")
@line_bp.route("/liff/home")
def liff_home():
    liff_id = os.getenv("LIFF_ID", "")
    return render_template("Line/liff_home.html", liff_id=liff_id)

@line_bp.route("/liff/profile")
def liff_profile():
    liff_id = os.getenv("LIFF_ID", "")
    return render_template("Line/liff_profile.html", liff_id=liff_id)

@line_bp.route("/liff/appointments")
def liff_appointments():
    liff_id = os.getenv("LIFF_ID", "")
    return render_template("Line/liff_appointments.html", liff_id=liff_id)

# --------- API สำหรับหน้า LIFF ---------
@line_bp.route("/api/profile")
def api_profile():
    supabase = get_db_client()
    if not supabase:
        return jsonify({"ok": False, "error": "database connection failed"}), 500
    
    user_id = request.args.get("userId")
    hn = request.args.get("hn")
    
    try:
        query = supabase.table("patients").select("id, hn, full_name, phone, birth_date, line_user_id")
        if user_id:
            query = query.eq("line_user_id", user_id)
        elif hn:
            query = query.eq("hn", hn)
        else:
            query = query.limit(1)

        res = query.limit(1).execute()
        if res.data and len(res.data) > 0:
            p = res.data[0]
            return jsonify({
                "ok": True,
                "full_name": p.get("full_name") or "",
                "name": p.get("full_name") or "",
                "hn": p.get("hn") or "",
                "phone": p.get("phone") or "",
                "birth_date": p.get("birth_date") or ""
            })
        return jsonify({"ok": False, "error": "ไม่พบข้อมูลผู้ป่วย"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@line_bp.route("/api/appointments")
def api_appointments():
    supabase = get_db_client()
    if not supabase:
        return jsonify({"ok": False, "error": "database connection failed"}), 500

    user_id = request.args.get("userId")
    hn = request.args.get("hn")

    try:
        patient_id = None
        if user_id:
            p_res = supabase.table("patients").select("id").eq("line_user_id", user_id).limit(1).execute()
            if p_res.data:
                patient_id = p_res.data[0]["id"]
            else:
                return jsonify({"ok": True, "data": []})
        elif hn:
            p_res = supabase.table("patients").select("id").eq("hn", hn).limit(1).execute()
            if p_res.data:
                patient_id = p_res.data[0]["id"]
            else:
                return jsonify({"ok": True, "data": []})

        q = supabase.table("appointments").select("appt_datetime, appt_type, status, note")
        if patient_id:
            q = q.eq("patient_id", patient_id)
        
        res = q.order("appt_datetime", desc=False).limit(10).execute()
        
        formatted_list = []
        for a in (res.data or []):
            dt_str = a.get("appt_datetime") or ""
            date_part = ""
            time_part = ""
            if "T" in dt_str:
                parts = dt_str.split("T")
                date_part = parts[0]
                time_part = parts[1][:5] if len(parts) > 1 else ""
            elif " " in dt_str:
                parts = dt_str.split(" ")
                date_part = parts[0]
                time_part = parts[1][:5] if len(parts) > 1 else ""
            else:
                date_part = dt_str

            formatted_list.append({
                "date": date_part,
                "time": time_part,
                "type": a.get("appt_type") or a.get("note") or "ตรวจติดตามอาการ",
                "status": a.get("status") or "รอยืนยัน",
                "note": a.get("note") or "",
                "appt_datetime": dt_str
            })

        return jsonify({
            "ok": True,
            "data": formatted_list
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
