from flask import Flask

from auth import auth_bp
from admin.routes_admin import admin_bp
from doctor.routes_doctor import doctor_bp
from nurse.routes_nurse import nurse_bp

app = Flask(__name__)
app.secret_key = "dev_secret_key"

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(nurse_bp)


@app.get("/")
def root():
    return "OK"


if __name__ == "__main__":
    app.run(debug=True)
