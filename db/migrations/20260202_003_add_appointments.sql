-- Appointments created by doctor

CREATE TABLE appointments (
  id INT AUTO_INCREMENT PRIMARY KEY,

  patient_id INT NOT NULL,
  encounter_id INT,             -- นัดจาก encounter ไหน (ถ้ามี)
  created_by_doctor INT NOT NULL,

  appt_datetime DATETIME NOT NULL,
  appt_type ENUM('followup','cga','other') DEFAULT 'followup',
  status ENUM('scheduled','completed','cancelled','no_show') DEFAULT 'scheduled',
  note TEXT,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (patient_id) REFERENCES patients(id),
  FOREIGN KEY (encounter_id) REFERENCES encounters(id),
  FOREIGN KEY (created_by_doctor) REFERENCES users(id),

  INDEX idx_appt_patient_time (patient_id, appt_datetime),
  INDEX idx_appt_doctor_time (created_by_doctor, appt_datetime)
);
