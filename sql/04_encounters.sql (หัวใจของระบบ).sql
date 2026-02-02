USE cga_system;

CREATE TABLE encounters (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  patient_id BIGINT UNSIGNED NOT NULL,

  created_by_nurse_id BIGINT UNSIGNED,
  assigned_doctor_id BIGINT UNSIGNED,

  encounter_datetime DATETIME DEFAULT CURRENT_TIMESTAMP,
  encounter_type ENUM('CGA','FollowUp','Other') DEFAULT 'CGA',
  status ENUM('draft','submitted','reviewed','closed') DEFAULT 'submitted',

  chief_complaint VARCHAR(255),
  nurse_summary TEXT,

  CONSTRAINT fk_enc_patient FOREIGN KEY (patient_id)
    REFERENCES patients(id),
  CONSTRAINT fk_enc_nurse FOREIGN KEY (created_by_nurse_id)
    REFERENCES users(id),
  CONSTRAINT fk_enc_doctor FOREIGN KEY (assigned_doctor_id)
    REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1 คน / 1 วัน = 1 encounter
ALTER TABLE encounters
  ADD COLUMN encounter_date DATE
  GENERATED ALWAYS AS (DATE(encounter_datetime)) STORED;

ALTER TABLE encounters
  ADD UNIQUE KEY uq_patient_per_day (patient_id, encounter_date);
