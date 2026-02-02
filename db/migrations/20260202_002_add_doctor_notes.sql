-- Doctor diagnosis & plan history

CREATE TABLE doctor_notes (
  id INT AUTO_INCREMENT PRIMARY KEY,

  encounter_id INT NOT NULL,
  doctor_id INT NOT NULL,

  diagnosis TEXT,          -- วินิจฉัย
  plan TEXT,               -- แผนการรักษา / คำแนะนำ
  followup_note TEXT,      -- หมายเหตุการติดตาม

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (encounter_id) REFERENCES encounters(id),
  FOREIGN KEY (doctor_id) REFERENCES users(id),

  INDEX idx_notes_encounter (encounter_id),
  INDEX idx_notes_doctor (doctor_id, created_at)
);
