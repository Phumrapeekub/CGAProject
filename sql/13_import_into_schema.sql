/* ============================================================
   CGA IMPORT (ONE-SHOT) : import_cga_1000 -> schema cga_system
   - Safe to re-run (idempotent)
   - Fix: no "ADD COLUMN IF NOT EXISTS" (MySQL 8 ใช้ไม่ได้กับ ADD COLUMN)
   - Fix: collation mismatch ด้วย COLLATE/CONVERT
   ============================================================ */

USE cga_system;

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

/* --------------------------
   0) Helpers: add column / add index if missing
   -------------------------- */
DROP PROCEDURE IF EXISTS sp_add_column_if_missing;
DELIMITER $$
CREATE PROCEDURE sp_add_column_if_missing(
  IN p_table VARCHAR(64),
  IN p_col   VARCHAR(64),
  IN p_ddl   TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = p_table
      AND COLUMN_NAME = p_col
  ) THEN
    SET @sql := p_ddl;
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_add_index_if_missing;
DELIMITER $$
CREATE PROCEDURE sp_add_index_if_missing(
  IN p_table VARCHAR(64),
  IN p_index VARCHAR(64),
  IN p_ddl   TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = p_table
      AND INDEX_NAME = p_index
  ) THEN
    SET @sql := p_ddl;
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

/* --------------------------
   1) Ensure required columns exist
   -------------------------- */
-- patients: emergency fields (ใช้ชื่อชุดเดียวให้ชัด)
CALL sp_add_column_if_missing(
  'patients','emergency_contact_name',
  'ALTER TABLE patients ADD COLUMN emergency_contact_name VARCHAR(255) NULL'
);
CALL sp_add_column_if_missing(
  'patients','emergency_contact_phone',
  'ALTER TABLE patients ADD COLUMN emergency_contact_phone VARCHAR(50) NULL'
);

-- encounters: encounter_date (ถ้าโปรเจคคุณมี unique ต่อวัน)
CALL sp_add_column_if_missing(
  'encounters','encounter_date',
  'ALTER TABLE encounters ADD COLUMN encounter_date DATE NULL'
);

-- assessment uniqueness (กันรันซ้ำไม่เพิ่มแถวซ้ำ)
CALL sp_add_index_if_missing(
  'patients','uq_patients_hn',
  'ALTER TABLE patients ADD UNIQUE KEY uq_patients_hn (hn)'
);
CALL sp_add_index_if_missing(
  'encounters','uq_enc_patient_day',
  'ALTER TABLE encounters ADD UNIQUE KEY uq_enc_patient_day (patient_id, encounter_date)'
);
CALL sp_add_index_if_missing(
  'assessment_headers','uq_header_enc_form',
  'ALTER TABLE assessment_headers ADD UNIQUE KEY uq_header_enc_form (encounter_id, form_code)'
);
CALL sp_add_index_if_missing(
  'assessment_items','uq_item_header_code',
  'ALTER TABLE assessment_items ADD UNIQUE KEY uq_item_header_code (assessment_header_id, item_code)'
);

/* --------------------------
   2) Upsert patients (INSERT ... ON DUPLICATE KEY UPDATE)
   - birth_date_raw ต้องเป็น YYYY-MM-DD ถึงจะแปลง ไม่งั้นเป็น NULL
   - citizen_id_raw ถ้าเป็น e+12 หรือเป็นตัวเลขล้วน -> แปลงเป็น 13 หลัก
   -------------------------- */
INSERT INTO patients
(
  hn, title_name, first_name, last_name, sex,
  birth_date, age_year,
  citizen_id, phone,
  address_text,
  emergency_contact_name, emergency_contact_phone
)
SELECT
  -- ทำให้ HN เป็น string ที่เทียบกันได้ชัด
  CONVERT(s.hn USING utf8mb4) AS hn,

  CASE
    WHEN s.title_name IN ('นาย','นาง','นางสาว','อื่นๆ') THEN s.title_name
    ELSE 'อื่นๆ'
  END AS title_name,

  s.first_name,
  s.last_name,

  CASE
    WHEN s.sex IN ('ชาย','หญิง','อื่นๆ','ไม่ระบุ') THEN s.sex
    ELSE 'ไม่ระบุ'
  END AS sex,

  CASE
    WHEN s.birth_date_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      THEN STR_TO_DATE(s.birth_date_raw, '%Y-%m-%d')
    ELSE NULL
  END AS birth_date,

  s.age_year,

  CASE
    -- รับทั้งเลขล้วน และรูปแบบ scientific (มี E/e)
    WHEN s.citizen_id_raw REGEXP '^[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
      THEN LPAD(
             CAST(CAST(s.citizen_id_raw AS DECIMAL(20,0)) AS CHAR),
             13,'0'
           )
    ELSE NULL
  END AS citizen_id,

  s.phone,
  s.address_text,

  s.caregiver_name,
  s.phone
FROM import_cga_1000 s
WHERE s.hn IS NOT NULL AND s.hn <> ''
ON DUPLICATE KEY UPDATE
  title_name = VALUES(title_name),
  first_name = VALUES(first_name),
  last_name  = VALUES(last_name),
  sex        = VALUES(sex),
  birth_date = VALUES(birth_date),
  age_year   = VALUES(age_year),
  citizen_id = VALUES(citizen_id),
  phone      = VALUES(phone),
  address_text = VALUES(address_text),
  emergency_contact_name  = VALUES(emergency_contact_name),
  emergency_contact_phone = VALUES(emergency_contact_phone);

/* --------------------------
   3) Insert encounters (1 encounter ต่อคนต่อวัน)
   - encounter_datetime = วันที่ประเมิน + 09:00:00
   - encounter_date = DATE(encounter_datetime)
   -------------------------- */
INSERT INTO encounters
(
  patient_id,
  created_by_nurse_id,
  assigned_doctor_id,
  encounter_datetime,
  encounter_date,
  encounter_type,
  status,
  chief_complaint,
  nurse_summary
)
SELECT
  p.id AS patient_id,
  NULL,
  NULL,

  STR_TO_DATE(CONCAT(s.assess_date_raw,' 09:00:00'), '%Y-%m-%d %H:%i:%s') AS encounter_datetime,
  STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d') AS encounter_date,

  'CGA',
  'submitted',
  NULL,
  CONCAT('นำเข้าจาก CSV | โรคประจำตัว: ',
         COALESCE(CONVERT(s.chronic_has USING utf8mb4),''), ' ',
         COALESCE(CONVERT(s.chronic_detail USING utf8mb4),''))
FROM import_cga_1000 s
JOIN patients p
  ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
WHERE s.assess_date_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
ON DUPLICATE KEY UPDATE
  -- ถ้ามีอยู่แล้ว อัปเดต note ได้
  nurse_summary = VALUES(nurse_summary),
  status       = VALUES(status);

/* (กันเคส encounter_date ยัง NULL จากของเดิม) */
UPDATE encounters
SET encounter_date = DATE(encounter_datetime)
WHERE encounter_date IS NULL AND encounter_datetime IS NOT NULL;

/* --------------------------
   4) Insert assessment_headers (BASIC / MMSE / TGDS / Q8 / HEARING / VISION / URINARY / SLEEP)
   -------------------------- */
-- BASIC
INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at, total_score, result_text)
SELECT
  e.id,
  'BASIC',
  '2568',
  e.encounter_datetime,
  NULL,
  CONCAT('edu=', COALESCE(CONVERT(s.education_level USING utf8mb4),''), ' | chronic=',
         COALESCE(CONVERT(s.chronic_has USING utf8mb4),''), ' ',
         COALESCE(CONVERT(s.chronic_detail USING utf8mb4),''))
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id = p.id AND e.encounter_date = STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE
  completed_at = VALUES(completed_at),
  result_text  = VALUES(result_text);

-- MMSE
INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at, total_score, result_text)
SELECT
  e.id, 'MMSE_T2002', '2568', e.encounter_datetime,
  s.mmse_score, s.mmse_result
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id = p.id AND e.encounter_date = STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE
  total_score = VALUES(total_score),
  result_text = VALUES(result_text);

-- TGDS
INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at, total_score, result_text)
SELECT
  e.id, 'TGDS15', '2568', e.encounter_datetime,
  s.tgds_score, s.tgds_result
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id = p.id AND e.encounter_date = STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE
  total_score = VALUES(total_score),
  result_text = VALUES(result_text);

-- 8Q
INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at, total_score, result_text)
SELECT
  e.id, 'Q8', '2568', e.encounter_datetime,
  s.q8_score, s.q8_risk_level
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id = p.id AND e.encounter_date = STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE
  total_score = VALUES(total_score),
  result_text = VALUES(result_text);

-- HEARING / VISION / URINARY / SLEEP (ไม่มีคะแนนก็ได้)
INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at)
SELECT e.id, 'HEARING', '2568', e.encounter_datetime
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE completed_at = VALUES(completed_at);

INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at)
SELECT e.id, 'VISION', '2568', e.encounter_datetime
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE completed_at = VALUES(completed_at);

INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at)
SELECT e.id, 'URINARY', '2568', e.encounter_datetime
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE completed_at = VALUES(completed_at);

INSERT INTO assessment_headers (encounter_id, form_code, form_version, completed_at)
SELECT e.id, 'SLEEP', '2568', e.encounter_datetime
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
ON DUPLICATE KEY UPDATE completed_at = VALUES(completed_at);

/* --------------------------
   5) Insert assessment_items (BASIC + HEARING + VISION + URINARY + SLEEP)
   -------------------------- */
-- BASIC items
INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'basic.education_level', 'ระดับการศึกษา', CONVERT(s.education_level USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='BASIC'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'basic.chronic_has', 'มีโรคประจำตัว', CONVERT(s.chronic_has USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='BASIC'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'basic.chronic_detail', 'รายละเอียดโรคประจำตัว', CONVERT(s.chronic_detail USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='BASIC'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

-- HEARING items
INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'hearing.left.result', 'ผลการได้ยินหูซ้าย', CONVERT(s.hearing_left_result USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='HEARING'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'hearing.left.note', 'รายละเอียดหูซ้าย', CONVERT(s.hearing_left_note USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='HEARING'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'hearing.right.result', 'ผลการได้ยินหูขวา', CONVERT(s.hearing_right_result USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='HEARING'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'hearing.right.note', 'รายละเอียดหูขวา', CONVERT(s.hearing_right_note USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='HEARING'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

-- VISION items
INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'vision.right.snellen', 'การมองเห็นตาขวา (Snellen)', CONVERT(s.vision_right_snellen USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='VISION'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'vision.left.snellen', 'การมองเห็นตาซ้าย (Snellen)', CONVERT(s.vision_left_snellen USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='VISION'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

-- URINARY item
INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'urinary.incontinence', 'ภาวะกลั้นปัสสาวะ', CONVERT(s.urinary_incontinence USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='URINARY'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

-- SLEEP item
INSERT INTO assessment_items (assessment_header_id, item_code, item_label, value_text)
SELECT h.id, 'sleep.problem', 'ปัญหาการนอน', CONVERT(s.sleep_problem USING utf8mb4)
FROM import_cga_1000 s
JOIN patients p ON p.hn COLLATE utf8mb4_unicode_ci = CONVERT(s.hn USING utf8mb4) COLLATE utf8mb4_unicode_ci
JOIN encounters e ON e.patient_id=p.id AND e.encounter_date=STR_TO_DATE(s.assess_date_raw,'%Y-%m-%d')
JOIN assessment_headers h ON h.encounter_id=e.id AND h.form_code='SLEEP'
ON DUPLICATE KEY UPDATE value_text = VALUES(value_text);

/* --------------------------
   6) Sanity checks
   -------------------------- */
SELECT
  (SELECT COUNT(*) FROM patients)          AS patients,
  (SELECT COUNT(*) FROM encounters)        AS encounters,
  (SELECT COUNT(*) FROM assessment_headers) AS headers,
  (SELECT COUNT(*) FROM assessment_items)  AS items;

SELECT form_code, COUNT(*) cnt
FROM assessment_headers
GROUP BY form_code
ORDER BY cnt DESC;

/* --------------------------
   7) Clean up helper procedures
   -------------------------- */
DROP PROCEDURE IF EXISTS sp_add_column_if_missing;
DROP PROCEDURE IF EXISTS sp_add_index_if_missing;

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;
