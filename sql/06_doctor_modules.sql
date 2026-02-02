USE cga_system;

CREATE TABLE doctor_notes (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT UNSIGNED NOT NULL,
  doctor_id BIGINT UNSIGNED NOT NULL,

  note_type ENUM('SOAP','Progress','Other') DEFAULT 'SOAP',
  subjective TEXT,
  objective TEXT,
  assessment TEXT,
  plan TEXT,

  signed_at DATETIME,

  CONSTRAINT fk_note_enc FOREIGN KEY (encounter_id)
    REFERENCES encounters(id),
  CONSTRAINT fk_note_doc FOREIGN KEY (doctor_id)
    REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
