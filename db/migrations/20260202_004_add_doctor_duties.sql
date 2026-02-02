-- Doctor duty schedule

CREATE TABLE doctor_duties (
  id INT AUTO_INCREMENT PRIMARY KEY,

  doctor_id INT NOT NULL,
  duty_date DATE NOT NULL,

  shift_type ENUM('day','evening','night','oncall') NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,

  location VARCHAR(120),
  note TEXT,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (doctor_id) REFERENCES users(id),

  UNIQUE KEY uq_doctor_shift (doctor_id, duty_date, shift_type),
  INDEX idx_duty_doctor_date (doctor_id, duty_date)
);
