import os
from flask import Blueprint, render_template, jsonify, request
from db.db import get_db_client

line_bp = Blueprint("line", __name__, url_prefix="/line")

# --------- หน้า LIFF ---------
@line_bp.route("/liff/profile")
def liff_profile():
    return render_template("Line/liff_profile.html")

@line_bp.route("/liff/appointments")
def liff_appointments():
    return render_template("Line/liff_appointments.html")

# --------- API สำหรับหน้า LIFF ---------
@line_bp.route("/api/profile")
def api_profile():
    supabase = get_db_client()
    if not supabase:
        return jsonify({"error": "database connection failed"}), 500
    try:
        res = supabase.table("patients").select("full_name, hn").limit(1).execute()
        if res.data:
            return jsonify({
                "name": res.data[0]["full_name"],
                "hn": res.data[0]["hn"]
            })
        return jsonify({"error": "no data"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@line_bp.route("/api/appointments")
def api_appointments():
    supabase = get_db_client()
    if not supabase:
        return jsonify({"error": "database connection failed"}), 500
    try:
        res = supabase.table("appointments").select("appt_datetime, status, note").limit(5).execute()
        return jsonify(res.data or [])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
