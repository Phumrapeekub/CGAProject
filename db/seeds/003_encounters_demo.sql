-- db/seeds/003_encounters_demo.sql
USE cga_system_dev;

-- กันโดน Safe Updates ขวางตอนลบข้อมูลเดโม
SET SQL_SAFE_UPDATES = 0;

-- ลบเฉพาะ encounter ที่เป็นของเดโม (ปลอดภัยกว่า TRUNCATE/DELETE ทั้งตาราง)
DELETE FROM encounters
WHERE note LIKE 'DEMO:%';

-- เลือกคนที่สร้าง encounter (เอา nurse_demo ถ้ามี ไม่งั้นใช้ nurse1)
SET @created_by := (
  SELECT id
  FROM users
  WHERE username IN ('nurse_demo','nurse1')
  ORDER BY (username='nurse_demo') DESC
  LIMIT 1
);

-- ใส่ encounters ให้ 5 คน (HN001–HN005)
-- (1) วันประเมิน CGA วันนี้
INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by, note)
VALUES
((SELECT id FROM patients WHERE hn='HN001' LIMIT 1), CURDATE(), 'cga', @created_by, 'DEMO:CGA today HN001'),
((SELECT id FROM patients WHERE hn='HN002' LIMIT 1), CURDATE(), 'cga', @created_by, 'DEMO:CGA today HN002'),
((SELECT id FROM patients WHERE hn='HN003' LIMIT 1), CURDATE(), 'cga', @created_by, 'DEMO:CGA today HN003'),
((SELECT id FROM patients WHERE hn='HN004' LIMIT 1), CURDATE(), 'cga', @created_by, 'DEMO:CGA today HN004'),
((SELECT id FROM patients WHERE hn='HN005' LIMIT 1), CURDATE(), 'cga', @created_by, 'DEMO:CGA today HN005');

-- (2) เพิ่ม follow-up บางคนให้เดโมดูสมจริง
INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by, note)
VALUES
((SELECT id FROM patients WHERE hn='HN001' LIMIT 1), DATE_SUB(CURDATE(), INTERVAL 30 DAY), 'followup', @created_by, 'DEMO:Follow-up -30d HN001'),
((SELECT id FROM patients WHERE hn='HN002' LIMIT 1), DATE_SUB(CURDATE(), INTERVAL 14 DAY), 'followup', @created_by, 'DEMO:Follow-up -14d HN002'),
((SELECT id FROM patients WHERE hn='HN004' LIMIT 1), DATE_SUB(CURDATE(), INTERVAL 7 DAY),  'other',    @created_by, 'DEMO:Other visit -7d HN004');

-- เปิด safe updates กลับ (นิสัยดีแบบระบบองค์กร)
SET SQL_SAFE_UPDATES = 1;

-- ตรวจผล
SELECT e.id, p.hn, e.encounter_date, e.encounter_type, e.created_by, e.note
FROM encounters e
JOIN patients p ON p.id = e.patient_id
WHERE e.note LIKE 'DEMO:%'
ORDER BY e.encounter_date DESC, p.hn;
