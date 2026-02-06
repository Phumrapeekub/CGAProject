-- db/seeds/004_assessment_sessions_demo.sql
USE cga_system_dev;

-- ปิด safe update ชั่วคราว (กัน Error 1175)
SET SQL_SAFE_UPDATES = 0;

-- หา user id ของคนสร้าง (เลือก nurse_demo ก่อน ถ้าไม่มีค่อยใช้ nurse1)
SET @created_by := (
  SELECT id
  FROM users
  WHERE username IN ('nurse_demo','nurse1')
  ORDER BY FIELD(username,'nurse_demo','nurse1')
  LIMIT 1
);

-- ลบเฉพาะ session เดโม (อิง encounter ที่ note ขึ้นต้น DEMO:)
DELETE s
FROM assessment_sessions s
JOIN encounters e ON e.id = s.encounter_id
WHERE e.note LIKE 'DEMO:%';

-- สร้าง session ให้ encounter เดโมทุกอัน (baseline + completed)
INSERT INTO assessment_sessions (encounter_id, session_type, assessed_at, status, created_by)
SELECT e.id, 'baseline', NOW(), 'completed', @created_by
FROM encounters e
WHERE e.note LIKE 'DEMO:%';

-- เปิด safe update กลับ
SET SQL_SAFE_UPDATES = 1;
