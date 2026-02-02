CREATE TABLE IF NOT EXISTS assessment_mmse (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cga_id INT NOT NULL,
  total_score INT DEFAULT 0,
  risk_level ENUM('normal','suspected') DEFAULT 'normal',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_mmse_cga
    FOREIGN KEY (cga_id) REFERENCES cga_headers(id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessment_mmse_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  mmse_id INT NOT NULL,
  section_no INT,
  question_no INT,
  answer_text TEXT,
  score INT DEFAULT 0,
  CONSTRAINT fk_mmse_items_mmse
    FOREIGN KEY (mmse_id) REFERENCES assessment_mmse(id)
    ON DELETE CASCADE
);
