USE cga_migration_test;

-- =========================================================
-- 012: audit_logs (บันทึกเหตุการณ์สำคัญในระบบ)
-- =========================================================
CREATE TABLE IF NOT EXISTS audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,

  actor_user_id INT NULL,                 -- users.id (คนที่ทำ)
  actor_role VARCHAR(30) NULL,            -- 'admin','doctor','nurse' (optional)

  action VARCHAR(50) NOT NULL,            -- 'create','update','delete','login','logout'
  entity_type VARCHAR(50) NOT NULL,       -- เช่น 'patient','cga_header','mmse','tgds'
  entity_id BIGINT NULL,                  -- id ของสิ่งที่ถูกกระทำ

  session_id INT NULL,                    -- ผูก session ได้
  cga_id INT NULL,                        -- ผูก cga ได้

  ip_address VARCHAR(45) NULL,            -- IPv4/IPv6
  user_agent VARCHAR(255) NULL,

  details_json JSON NULL,                 -- รายละเอียดเพิ่มเติม (ยืดหยุ่น)
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_audit_actor
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
    ON DELETE SET NULL,

  CONSTRAINT fk_audit_session
    FOREIGN KEY (session_id) REFERENCES assessment_sessions(id)
    ON DELETE SET NULL,

  CONSTRAINT fk_audit_cga
    FOREIGN KEY (cga_id) REFERENCES cga_headers(id)
    ON DELETE SET NULL
);

CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_session ON audit_logs(session_id);
CREATE INDEX idx_audit_cga ON audit_logs(cga_id);
