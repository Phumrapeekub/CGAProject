-- 20260202_007_add_assessment_sessions.sql
-- Purpose: รองรับการประเมินซ้ำ (3/6/12 เดือน) + ทำรายงานง่ายขึ้น

USE cga_migration_test;

CREATE TABLE IF NOT EXISTS assessment_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,

  -- ผูกกับ encounter (มีอยู่ใน 01_schema ของคุณแล้ว)
  encounter_id INT NOT NULL,

  -- รอบการประเมิน: baseline / 3m / 6m / 12m / adhoc
  session_type ENUM('baseline','3m','6m','12m','adhoc') NOT NULL DEFAULT 'baseline',

  -- วันที่ประเมินจริง (เอาไว้กรองรายงาน)
  assessed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- สถานะรอบนี้
  status ENUM('draft','completed','void') NOT NULL DEFAULT 'completed',

  -- ผู้บันทึก (optional)
  created_by INT NULL,  -- อาจผูก users.id ถ้าต้องการ

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_session_encounter
    FOREIGN KEY (encounter_id) REFERENCES encounters(id)
    ON DELETE CASCADE
);

-- index ช่วย query เร็วขึ้น
CREATE INDEX idx_sessions_encounter ON assessment_sessions(encounter_id);
CREATE INDEX idx_sessions_assessed_at ON assessment_sessions(assessed_at);
