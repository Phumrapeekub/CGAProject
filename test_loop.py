from db.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM assessment_answers WHERE session_id=184")
ans_rows = cur.fetchall()
basic_extras = {}
for row in ans_rows:
    inst = str(row.get("instrument") or "").lower()
    q_no = row.get("question_no")
    val = row.get("answer_int") if row.get("answer_int") is not None else row.get("answer_text")
    txt = str(row.get("answer_text") or "").lower()
    if inst == "basic":
        print(f"BASIC! val={val} type={type(val)}")
        if val and isinstance(val, str):
            if val.startswith("live:"):
                l = val.split(":", 1)[1]
                basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
            elif val.startswith("height:"):
                basic_extras["height"] = val.split(":", 1)[1]
            elif val.startswith("waist:"):
                basic_extras["waist"] = val.split(":", 1)[1]
print(basic_extras)
