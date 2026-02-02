USE cga_migration_test;

-- เพิ่ม session_id ให้ cga_headers เพื่อผูกหัว CGA กับ session
ALTER TABLE cga_headers
  ADD COLUMN session_id INT NULL AFTER encounter_id;

ALTER TABLE cga_headers
  ADD CONSTRAINT fk_cga_headers_session
    FOREIGN KEY (session_id) REFERENCES assessment_sessions(id)
    ON DELETE SET NULL;

CREATE INDEX idx_cga_headers_session ON cga_headers(session_id);
