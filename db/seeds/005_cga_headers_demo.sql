-- db/seeds/005_cga_headers_demo.sql
USE cga_system_dev;

-- ลบเฉพาะ header เดโม (กันรันซ้ำแล้วรก)
SET SQL_SAFE_UPDATES = 0;
DELETE FROM cga_headers
WHERE note LIKE 'DEMO:%';
SET SQL_SAFE_UPDATES = 1;

-- doctor ผู้ประเมิน
SET @doctor_id := (
  SELECT id FROM users
  WHERE username IN ('doctor_demo','doctor1')
  ORDER BY (username='doctor_demo') DESC
  LIMIT 1
);

-- map session ต่อ encounter (ของเดโมวันนี้)
INSERT INTO cga_headers (encounter_id, session_id, assessed_by, assessed_at, overall_risk, note)
SELECT
  e.id AS encounter_id,
  s.id AS session_id,
  @doctor_id AS assessed_by,
  NOW() AS assessed_at,
  'low' AS overall_risk,
  CONCAT('DEMO:HEADER for encounter ', e.id) AS note
FROM encounters e
JOIN assessment_sessions s ON s.encounter_id = e.id
WHERE e.note LIKE 'DEMO:%'
  AND e.encounter_type = 'cga'
  AND e.encounter_date = CURDATE()
ON DUPLICATE KEY UPDATE
  session_id   = VALUES(session_id),
  assessed_by  = VALUES(assessed_by),
  assessed_at  = VALUES(assessed_at),
  overall_risk = VALUES(overall_risk),
  note         = VALUES(note);
