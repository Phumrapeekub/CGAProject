USE cga_migration_test;

-- =========================================================
-- 009: assessment_answers (คำตอบรายข้อแบบกลาง)
-- =========================================================
CREATE TABLE IF NOT EXISTS assessment_answers (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,

  session_id INT NOT NULL,
  cga_id INT NULL,

  instrument VARCHAR(50) NOT NULL,     -- เช่น 'mmse','tgds','sra','8q'
  question_no INT NOT NULL,            -- ข้อที่ 1..n
  answer_int INT NULL,                 -- 0/1 หรือคะแนน
  answer_text TEXT NULL,               -- คำตอบแบบข้อความ
  score INT DEFAULT 0,                 -- คะแนนที่ได้จากข้อนั้น

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_answers_session
    FOREIGN KEY (session_id) REFERENCES assessment_sessions(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_answers_cga
    FOREIGN KEY (cga_id) REFERENCES cga_headers(id)
    ON DELETE SET NULL
);

CREATE INDEX idx_answers_session ON assessment_answers(session_id);
CREATE INDEX idx_answers_instrument ON assessment_answers(instrument);
CREATE INDEX idx_answers_session_instrument ON assessment_answers(session_id, instrument);
