USE cga_system;

CREATE TABLE assessment_headers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT UNSIGNED NOT NULL,

  form_code VARCHAR(50) NOT NULL,
  form_version VARCHAR(20),
  completed_by_user_id BIGINT UNSIGNED,
  completed_at DATETIME,

  total_score DECIMAL(10,2),
  result_text VARCHAR(255),

  CONSTRAINT fk_assess_enc FOREIGN KEY (encounter_id)
    REFERENCES encounters(id),
  CONSTRAINT fk_assess_user FOREIGN KEY (completed_by_user_id)
    REFERENCES users(id),

  UNIQUE KEY uq_form_per_encounter (encounter_id, form_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE assessment_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  assessment_header_id BIGINT UNSIGNED NOT NULL,

  item_code VARCHAR(80) NOT NULL,
  item_label VARCHAR(255),
  value_text TEXT,
  value_number DECIMAL(12,4),
  value_bool TINYINT,

  CONSTRAINT fk_item_header FOREIGN KEY (assessment_header_id)
    REFERENCES assessment_headers(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
