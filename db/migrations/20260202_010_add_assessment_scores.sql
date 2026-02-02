USE cga_migration_test;

-- =========================================================
-- 010: assessment_scores (สรุปคะแนนรวม/ความเสี่ยงต่อแบบประเมิน)
-- =========================================================
CREATE TABLE IF NOT EXISTS assessment_scores (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,

  session_id INT NOT NULL,
  cga_id INT NULL,

  instrument VARCHAR(50) NOT NULL,      -- 'mmse','tgds','sra','8q' ...
  total_score INT DEFAULT 0,
  risk_level VARCHAR(30) NULL,          -- 'normal','mild','moderate','severe' หรือ 'low/med/high'
  note TEXT NULL,

  computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_scores_session
    FOREIGN KEY (session_id) REFERENCES assessment_sessions(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_scores_cga
    FOREIGN KEY (cga_id) REFERENCES cga_headers(id)
    ON DELETE SET NULL,

  -- กันซ้ำ: 1 session + 1 instrument ควรมีสรุปแถวเดียว
  UNIQUE KEY uq_scores_session_instrument (session_id, instrument)
);

CREATE INDEX idx_scores_session ON assessment_scores(session_id);
CREATE INDEX idx_scores_instrument ON assessment_scores(instrument);
CREATE INDEX idx_scores_risk ON assessment_scores(risk_level);
