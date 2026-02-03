from flask import Flask

# ✅ import blueprints (ปรับ path ให้ตรงกับของคุณ)
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp

def create_app():
    app = Flask(__name__)
    app.secret_key = "dev-secret-key"

    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(nurse_bp)

    @app.get("/")
    def home():
        return "CGAProject OK"

    return app

if __name__ == "__main__":
    create_app().run(debug=True)
