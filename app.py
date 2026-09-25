from __future__ import annotations
import os
import sys
import io
import traceback
from datetime import timedelta
from flask import Flask, redirect, render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
load_dotenv()

# Prevent UnicodeEncodeError on Windows console when printing Thai or emojis
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp
from Line.routes_line import line_bp

app = Flask(__name__)

# ProxyFix for reverse proxy (HTTPS on Hugging Face Spaces)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev_secret_key_cga_hospital_phayao_2026"

def parse_dt(d):
    if not d: return None
    from datetime import datetime
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d.replace('Z', '+00:00'))
        except:
            return None
    return d

app.jinja_env.globals.update(parse_dt=parse_dt)

# ตั้งค่า Session Cookie ให้ทำงานได้ทั้ง Direct URL และเมื่อฝังใน iframe ของ Hugging Face Spaces
is_hf_space = bool(os.getenv("SPACE_ID")) or os.getenv("ENV") == "production"
app.config.update(
    SESSION_COOKIE_SECURE=True if is_hf_space else False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None' if is_hf_space else 'Lax',
    SESSION_COOKIE_NAME='cga_session',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # อนุญาตให้ Hugging Face Spaces ฝัง iframe ได้โดยไม่โดนเบราว์เซอร์บล็อก
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' https://huggingface.co https://*.huggingface.co https://*.hf.space;"
    return response

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(nurse_bp)
app.register_blueprint(line_bp)

@app.get("/")
def root():
    return redirect("/login")

@app.errorhandler(404)
def not_found_error(e):
    return (
        "<div style='font-family:sans-serif;padding:36px;max-width:550px;margin:60px auto;background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.05);'>"
        "<h2 style='margin-top:0;color:#1e293b;font-size:24px;'>🔍 ไม่พบหน้าที่ต้องการ (404)</h2>"
        "<p style='color:#64748b;font-size:15px;line-height:1.6;'>ไม่พบหน้าที่คุณเรียกดู หรือหน้านี้อาจถูกย้ายไปแล้ว</p>"
        "<a href='/login' style='display:inline-block;margin-top:16px;background:#2563eb;color:#fff;padding:10px 24px;border-radius:10px;text-decoration:none;font-weight:bold;'>กลับสู่ระบบ</a>"
        "</div>",
        404
    )

@app.errorhandler(500)
def internal_error(e):
    trace = traceback.format_exc()
    print("500 Internal Error Traceback:\n", trace)
    return (
        "<div style='font-family:sans-serif;padding:36px;max-width:580px;margin:60px auto;background:#fff1f2;border:1px solid #fecdd3;border-radius:16px;color:#9f1239;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.05);'>"
        "<h2 style='margin-top:0;color:#9f1239;font-size:24px;'>⚠️ เกิดข้อผิดพลาดของระบบ (500)</h2>"
        "<p style='color:#4b5563;font-size:15px;line-height:1.6;'>ระบบพบปัญหาในการประมวลผลคำขอของคุณ กรุณาลองใหม่อีกครั้ง หรือติดต่อผู้ดูแลระบบ</p>"
        "<a href='/login' style='display:inline-block;margin-top:16px;background:#e11d48;color:#fff;padding:10px 24px;border-radius:10px;text-decoration:none;font-weight:bold;'>กลับสู่หน้าเข้าสู่ระบบ</a>"
        "</div>",
        500
    )

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 8080)))