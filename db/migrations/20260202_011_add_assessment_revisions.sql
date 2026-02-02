USE cga_migration_test;

-- =========================================================
-- 011: assessment_revisions (เก็บเวอร์ชัน/ประวัติการแก้ไข)
-- =========================================================
CREATE TABLE IF NOT EXISTS assessment_revisions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,

  session_id INT NOT NULL,
  cga_id INT NULL,

  instrument VARCHAR(50) NULL,        -- ถ้าแก้เฉพาะแบบ เช่น 'mmse'
  revision_no INT NOT NULL DEFAULT 1, -- ลำดับเวอร์ชัน

  change_type ENUM('create','update','delete') NOT NULL DEFAULT 'update',
  changed_by INT NULL,                -- users.id (ถ้ายังไม่ใช้ก็ปล่อย NULL ได้)
  changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- เก็บ snapshot/รายละเอียดการเปลี่ยนแปลง
  snapshot_json JSON NULL,
  note TEXT NULL,

  CONSTRAINT fk_rev_session
    FOREIGN KEY (session_id) REFERENCES assessment_sessions(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_rev_cga
    FOREIGN KEY (cga_id) REFERENCES cga_headers(id)
    ON DELETE SET NULL
);

CREATE INDEX idx_rev_session ON assessment_revisions(session_id);
CREATE INDEX idx_rev_instrument ON assessment_revisions(instrument);
CREATE INDEX idx_rev_changed_at ON assessment_revisions(changed_at);
