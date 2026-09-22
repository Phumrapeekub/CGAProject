from flask import Blueprint, render_template, jsonify, request
from supabase import create_client
import os

line_bp = Blueprint("line", __name__, url_prefix="")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Exception("❌ Supabase env not set (SUPABASE_URL / SUPABASE_KEY)")
    return create_client(SUPABASE_URL, SUPABASE_KEY)
# --------- หน้า LIFF ---------
@line_bp.route("/liff/profile")
def liff_profile():
    return render_template("line/liff_profile.html")

@line_bp.route("/liff/appointments")
def liff_appointments():
    return render_template("line/liff_appointments.html")


# --------- API สำหรับหน้า LIFF ---------
@line_bp.route("/api/profile")
def api_profile():
    # ตัวอย่าง: ดึงข้อมูลผู้ใช้จาก Supabase (ปรับตามตารางจริงของเธอ)
    res = supabase.table("patients").select("full_name, hn").limit(1).execute()

    if res.data:
        return jsonify({
            "name": res.data[0]["full_name"],
            "hn": res.data[0]["hn"]
        })
    else:
        return jsonify({"error": "no data"}), 404


@line_bp.route("/api/appointments")
def api_appointments():
    res = supabase.table("appointments").select("date, time, doctor").limit(5).execute()
    return jsonify(res.data)
from flask import Blueprint, render_template, jsonify
from supabase import create_client
import os

line_bp = Blueprint("line", __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Exception("❌ Supabase env not set (SUPABASE_URL / SUPABASE_KEY)")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@line_bp.route("/liff/profile")
def liff_profile():
    return render_template("line/liff_profile.html")

@line_bp.route("/liff/appointments")
def liff_appointments():
    return render_template("line/liff_appointments.html")

@line_bp.route("/api/profile")
def api_profile():
    supabase = get_supabase()
    res = supabase.table("patients").select("full_name, hn").limit(1).execute()
    if res.data:
        return jsonify(res.data[0])
    return jsonify({"error": "no data"}), 404
