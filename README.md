# 🏥 CGA Project: Comprehensive Geriatric Assessment System
**ระบบประเมินสุขภาพผู้สูงอายุแบบครบวงจร โรงพยาบาลพะเยา**

ระบบบริหารจัดการการตรวจประเมินสุขภาพผู้สูงอายุ (CGA) ที่รวมเทคโนโลยี Web Application เข้ากับการวิเคราะห์ข้อมูลด้วย AI (Machine Learning) เพื่อช่วยให้บุคลากรทางการแพทย์ทำงานได้อย่างมีประสิทธิภาพ

---

## ✨ คุณสมบัติหลัก (Key Features)
- 🔐 **ระบบจัดการสิทธิ์ (RBAC):** แยกการทำงานตามบทบาท (Admin, Doctor, Nurse)
- 📋 **การประเมิน CGA:** ระบบบันทึกข้อมูลและคำนวณคะแนนแบบประเมิน (MMSE, TGDS, ADL ฯลฯ)
- 🤖 **AI Risk Analysis:** วิเคราะห์ความเสี่ยงรายบุคคลด้วยโมเดล H2O AutoML
- 📈 **Medical Dashboard:** สรุปสถิติและภาพรวมสุขภาพผู้ป่วยในรูปแบบกราฟที่เข้าใจง่าย
- 📅 **ระบบนัดหมายและตารางเวร:** จัดการนัดหมายคนไข้และตารางการปฏิบัติงานของแพทย์

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
D:\CGAProject\
├── 📄 app.py                # จุดเริ่มต้นแอปพลิเคชัน (Flask Entry Point)
├── 📄 README.md             # คู่มือการใช้งานโปรเจกต์
├── 📄 requirements.txt      # รายการ Library ที่จำเป็น
├── 📁 admin/                # โมดูลผู้ดูแลระบบ (Dashboard สถิติรวม, จัดการ User)
├── 📁 auth/                 # ระบบยืนยันตัวตน (Login, Session Management)
├── 📁 doctor/               # โมดูลแพทย์ (วินิจฉัย, นัดหมาย, ตารางเวร)
├── 📁 nurse/                # โมดูลพยาบาล (บันทึกคนไข้, ทำแบบประเมิน CGA)
├── 📁 db/                   # การตั้งค่าฐานข้อมูล
│   └── 📁 migrations/       # SQL Scripts สำหรับอัปเดต Schema
├── 📁 ml/                   # ระบบ Machine Learning (H2O.ai)
│   ├── 📁 models/           # จัดเก็บไฟล์โมเดลที่เทรนเสร็จแล้ว (.zip, binary)
│   ├── 📁 plots/            # กราฟวิเคราะห์ (ROC Curve, Feature Importance)
│   ├── 📁 metrics/          # ข้อมูลดิบด้านประสิทธิภาพ (JSON, CSV)
│   ├── 📄 step1_check.py    # สคริปต์ตรวจสอบข้อมูลก่อนเทรน
│   └── 📄 step2_train.py    # สคริปต์ฝึกสอนโมเดล AutoML
├── 📁 data/                 # แหล่งเก็บข้อมูล CSV สำหรับ Training & Staging
├── 📁 scripts/              # สคริปต์ Utility (เช่น การนำเข้าข้อมูลจาก CSV)
├── 📁 sql/                  # รวมไฟล์ SQL สำหรับสร้างฐานข้อมูลเริ่มต้น
├── 📁 static/               # ไฟล์ Assets (CSS, JS, Images, ML Plots)
├── 📁 templates/            # HTML Templates (Jinja2) แยกตามโมดูล
└── 📁 python_CGA/           # ตัวอย่างโปรแกรมต้นแบบ (Desktop Prototype)
```

---

## 🛠 เทคโนโลยีที่ใช้ (Tech Stack)
- **Backend:** Python (Flask Framework)
- **Database:** MySQL
- **AI/ML:** H2O.ai AutoML, Pandas, NumPy
- **Frontend:** HTML5, CSS3, JavaScript, Jinja2, Bootstrap
- **Tools:** Python-Dotenv, Matplotlib (for ML plots)

---

## 🚀 การติดตั้งและเริ่มใช้งาน (Setup & Installation)

### 1. การเตรียมสภาพแวดล้อม
```bash
# สร้าง Virtual Environment
python -m venv .venv

# Activate สภาพแวดล้อม (Windows)
.venv\Scripts\activate
```

### 2. การติดตั้ง Library
```bash
pip install -r requirements.txt
```

### 3. การตั้งค่าฐานข้อมูล
1. นำไฟล์ใน `sql/` หรือ `db/migrations/` ไปรันใน MySQL Server
2. สร้างไฟล์ `.env` ที่ Root เพื่อตั้งค่า Database:
   ```env
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=cga_system_dev
   ```

### 4. การรันระบบ
```bash
# รัน Web Server
python app.py
```
เข้าใช้งานผ่าน Browser: `http://127.0.0.1:5000`

---

## 📊 ส่วนของ Machine Learning
หากต้องการอัปเดตโมเดลหรือตรวจสอบข้อมูล:
1. เตรียมข้อมูลใน `data/`
2. ตรวจสอบข้อมูล: `python ml/step1_check_data.py`
3. ฝึกสอนโมเดลใหม่: `python ml/step2_train_automl.py`
*ผลลัพธ์โมเดลและกราฟจะถูกจัดเก็บในโฟลเดอร์ `ml/models/` และ `ml/plots/`*

---
© 2026 CGA Project - พัฒนาเพื่อสนับสนุนการดูแลสุขภาพผู้สูงอายุอย่างยั่งยืน