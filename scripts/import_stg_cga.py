import pandas as pd
import psycopg2
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = Path(__file__).parent.parent / "data" / "CGA_1000HN.csv"   # <-- ชื่อไฟล์คุณ (อยู่โฟลเดอร์เดียวกับไฟล์นี้)
TABLE    = "stg_cga_csv"

# ----- 1) อ่าน CSV แบบชัวร์ ไม่เพี้ยน -----
def read_csv_safely(path: Path) -> pd.DataFrame:
    encodings_to_try = ["utf-8-sig", "utf-8", "cp874", "tis-620", "windows-1252", "latin1"]
    last_err = None
    for enc in encodings_to_try:
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
            print(f"✅ CSV read ok with encoding: {enc}")
            return df
        except Exception as e:
            last_err = e
    raise last_err

# ----- 2) map ชื่อคอลัมน์ไทย -> อังกฤษ (ตรงกับ header ที่คุณส่งมา) -----
COLMAP = {
    "HN": "hn",
    "คำนำหน้า": "prefix",
    "ชื่อ": "first_name",
    "สกุล": "last_name",
    "เลขบัตรประชาชน": "citizen_id",
    "วันเดือนปีเกิด": "dob_text",
    "อายุ": "age",
    "ระดับการศึกษา": "education",
    "เพศ": "sex",
    "บ้านเลขที่": "house_no",
    "หมู่": "moo",
    "ตำบล": "subdistrict",
    "อำเภอ": "district",
    "จังหวัด": "province",
    "ที่อยู่รวม": "full_address",
    "ชื่อผู้ดูแล": "caregiver_name",
    "เบอร์โทรศัพท์": "phone",
    "มีโรคประจำตัว": "has_comorbidity",
    "รายละเอียดโรคประจำตัว": "comorbidity_detail",
    "คะแนน MMSE": "mmse_score",
    "ผล MMSE": "mmse_result",
    "คะแนน TGDS": "tgds_score",
    "ผล TGDS": "tgds_result",
    "คะแนน 8Q": "q8_score",
    "ระดับความเสี่ยงฆ่าตัวตาย": "suicide_risk_level",
    "ผลการได้ยินหูซ้าย": "hearing_left_result",
    "รายละเอียดหูซ้าย": "hearing_left_detail",
    "ผลการได้ยินหูขวา": "hearing_right_result",
    "รายละเอียดหูขวา": "hearing_right_detail",
    "การมองเห็นตาขวา (Snellen)": "vision_right_snellen",
    "การมองเห็นตาซ้าย (Snellen)": "vision_left_snellen",
    "ภาวะกลั้นปัสสาวะ": "incontinence",
    "ปัญหาการนอน": "sleep_problem",
    "วันที่ประเมิน": "assessed_date_text",
}

CREATE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE IF NOT EXISTS {TABLE} (
  id SERIAL PRIMARY KEY,
  hn VARCHAR(20),

  prefix VARCHAR(20),
  first_name VARCHAR(100),
  last_name VARCHAR(100),
  citizen_id TEXT,

  dob_text VARCHAR(50),
  age INT,
  education VARCHAR(100),
  sex VARCHAR(20),

  house_no VARCHAR(30),
  moo VARCHAR(30),
  subdistrict VARCHAR(100),
  district VARCHAR(100),
  province VARCHAR(100),
  full_address TEXT,

  caregiver_name VARCHAR(150),
  phone VARCHAR(50),

  has_comorbidity VARCHAR(20),
  comorbidity_detail TEXT,

  mmse_score INT,
  mmse_result VARCHAR(100),
  tgds_score INT,
  tgds_result VARCHAR(100),
  q8_score INT,
  suicide_risk_level VARCHAR(150),

  hearing_left_result VARCHAR(100),
  hearing_left_detail TEXT,
  hearing_right_result VARCHAR(100),
  hearing_right_detail TEXT,

  vision_right_snellen VARCHAR(50),
  vision_left_snellen VARCHAR(50),

  incontinence VARCHAR(100),
  sleep_problem VARCHAR(100),

  assessed_date_text VARCHAR(50)
);

CREATE INDEX idx_hn ON {TABLE} (hn);
"""

def to_int(x):
    x = (x or "").strip()
    if x == "":
        return None
    try:
        return int(float(x))
    except:
        return None

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"❌ ไม่เจอไฟล์: {CSV_PATH.resolve()}")

    df = read_csv_safely(CSV_PATH)

    # rename ไทย -> อังกฤษ
    df = df.rename(columns=COLMAP)

    # keep only known columns
    cols = list(COLMAP.values())
    df = df[[c for c in cols if c in df.columns]]

    # convert numeric cols
    for c in ["age", "mmse_score", "tgds_score", "q8_score"]:
        if c in df.columns:
            df[c] = df[c].apply(to_int)

    # connect Supabase
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "db.ylahheyefrqxcjqccpsn.supabase.co"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "Kantiya203_"),
        database=os.getenv("DB_NAME", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )
    cur = conn.cursor()

    # create table
    cur.execute(CREATE_SQL)
    conn.commit()

    # insert
    insert_cols = df.columns.tolist()
    placeholders = ",".join(["%s"] * len(insert_cols))
    col_sql = ",".join([f'"{c}"' for c in insert_cols])

    sql = f"INSERT INTO {TABLE} ({col_sql}) VALUES ({placeholders})"

    # Clean data: Replace NaN with None for psycopg2
    df = df.where(pd.notnull(df), None)
    rows = [tuple(x) for x in df.values]
    
    BATCH = 500
    total = 0

    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        cur.executemany(sql, batch)
        conn.commit()
        total += len(batch)
        print(f"✅ inserted: {total}/{len(rows)}")

    cur.close()
    conn.close()

    print(f"🎉 DONE: Imported {len(rows)} rows into {TABLE}")

if __name__ == "__main__":
    main()