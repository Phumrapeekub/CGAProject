from __future__ import annotations
import os, shutil
from flask import Flask, redirect, jsonify
from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp
from Line.routes_line import line_bp
from supabase_utils import check_supabase_connection
from dotenv import load_dotenv
load_dotenv()


def ensure_mariadb_running():
    if os.name == 'nt':
        return  # On Windows, local MySQL runs as Windows Service
    
    import socket, subprocess, time
    sock_path = "/tmp/mysql.sock"
    if os.path.exists(sock_path):
        return
        
    mariadb_bin = "/usr/sbin/mariadbd" if os.path.exists("/usr/sbin/mariadbd") else "mariadbd"
    datadir = "/app/mariadb/data"
    if os.path.exists(datadir):
        try:
            print("Starting embedded MariaDB daemon from Python...")
            subprocess.Popen([
                mariadb_bin,
                f"--datadir={datadir}",
                f"--socket={sock_path}",
                "--port=3306",
                "--bind-address=0.0.0.0"
            ])
            for _ in range(25):
                if os.path.exists(sock_path):
                    print("Embedded MariaDB is ready via socket!")
                    break
                time.sleep(0.4)
        except Exception as e:
            print("Failed to launch embedded MariaDB:", e)

ensure_mariadb_running()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_fallback")

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

# ตั้งค่าให้ Session ทำงานได้เมื่อฝังเว็บใน iframe ของ Hugging Face Spaces
is_hf_space = bool(os.getenv("SPACE_ID"))
app.config.update(
    SESSION_COOKIE_SECURE=is_hf_space,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None' if is_hf_space else 'Lax',
)

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(nurse_bp)
app.register_blueprint(line_bp)

@app.get("/")
def root():
    return redirect("/login")

@app.get("/check-supabase")
def supabase_status():
    result = check_supabase_connection()
    return jsonify(result)

@app.get("/debug-db")
def debug_db():
    import subprocess, socket
    db_env = {
        "DB_HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "DB_USER": os.getenv("DB_USER", "root"),
        "DB_PORT": os.getenv("DB_PORT", "3306"),
        "DB_NAME": os.getenv("DB_NAME", "cga_system_dev"),
        "DB_PASSWORD_IS_SET": bool(os.getenv("DB_PASSWORD")),
    }
    
    # 1. Check socket 3306
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    port_3306_open = (sock.connect_ex(('127.0.0.1', 3306)) == 0)
    sock.close()
    
    # 2. Try connect to env DB_HOST with SSL and without SSL
    from db.db import get_db_connection
    import mysql.connector
    
    results = {}
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "root")
    pwd = os.getenv("DB_PASSWORD")
    db = os.getenv("DB_NAME", "cga_system_dev")

    for ssl_mode in [False, True]:
        try:
            c = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=pwd,
                database=db,
                ssl_disabled=ssl_mode,
                connect_timeout=5
            )
            cur = c.cursor()
            cur.execute("SHOW TABLES")
            tables = [r[0] for r in cur.fetchall()]
            results[f"env_host_ssl_disabled_{ssl_mode}"] = {
                "status": "SUCCESS",
                "table_count": len(tables),
                "tables": tables
            }
            c.close()
        except Exception as err:
            results[f"env_host_ssl_disabled_{ssl_mode}"] = str(err)
    # 3. Test actual get_db_connection()
    real_conn_status = "FAILED"
    real_conn_tables = 0
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SHOW TABLES")
            real_conn_tables = len(cur.fetchall())
            real_conn_status = "SUCCESS"
            conn.close()
    except Exception as e:
        real_conn_status = str(e)
    results["get_db_connection_result"] = {
        "status": real_conn_status,
        "tables": real_conn_tables
    }
    
    # 4. Check processes and filesystem
    proc_list = ""
    try:
        proc_list = subprocess.check_output(["ps", "aux"], text=True)
    except Exception as e:
        proc_list = str(e)

    diag = {
        "mariadbd_exists": os.path.exists("/usr/sbin/mariadbd"),
        "mariadb_in_path": shutil.which("mariadbd") or shutil.which("mysqld"),
        "app_mariadb_exists": os.path.exists("/app/mariadb"),
        "app_mariadb_data_exists": os.path.exists("/app/mariadb/data"),
        "app_mariadb_data_contents": os.listdir("/app/mariadb/data") if os.path.exists("/app/mariadb/data") else [],
        "var_lib_mysql_exists": os.path.exists("/var/lib/mysql"),
        "var_lib_mysql_contents": os.listdir("/var/lib/mysql") if os.path.exists("/var/lib/mysql") else [],
    }
    
    # Try starting it right now synchronously and return output
    start_output = ""
    try:
        res = subprocess.run([
            shutil.which("mariadbd") or "mariadbd",
            "--datadir=/app/mariadb/data",
            "--socket=/tmp/mysql.sock",
            "--port=3306",
            "--bind-address=0.0.0.0"
        ], capture_output=True, text=True, timeout=3)
        start_output = f"stdout: {res.stdout}\nstderr: {res.stderr}"
    except subprocess.TimeoutExpired:
        start_output = "Started and timed out (running!)"
    except Exception as e:
        start_output = str(e)
    diag["sync_start_attempt"] = start_output

    return jsonify({
        "env": db_env,
        "port_3306_open": port_3306_open,
        "connection_tests": results,
        "diag": diag,
        "processes": proc_list
    })

@app.errorhandler(500)
def internal_error(e):
    import traceback
    trace = traceback.format_exc()
    print("500 Internal Error Traceback:\n", trace)
    return f"<div style='font-family:sans-serif;padding:30px;max-width:850px;margin:40px auto;background:#fff1f2;border:1px solid #fecdd3;border-radius:16px;color:#9f1239;'><h2 style='margin-top:0;'>⚠️ Server Error (500)</h2><p>เกิดข้อผิดพลาดในการประมวลผลคำขอ:</p><pre style='background:#fff;padding:15px;border-radius:8px;overflow-x:auto;border:1px solid #fda4af;font-size:13px;line-height:1.5;'>{trace}</pre><a href='/login' style='display:inline-block;margin-top:15px;background:#e11d48;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;'>กลับสู่หน้าเข้าสู่ระบบ</a></div>", 500

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 8080)))