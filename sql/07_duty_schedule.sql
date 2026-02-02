USE cga_system;

CREATE TABLE duty_shifts (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  shift_date DATE NOT NULL,
  shift_type ENUM('morning','evening','night','oncall') NOT NULL,
  location VARCHAR(255),

  UNIQUE KEY uq_shift (shift_date, shift_type, location)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE duty_shift_assignments (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  duty_shift_id BIGINT UNSIGNED NOT NULL,
  doctor_id BIGINT UNSIGNED NOT NULL,

  attendance_status ENUM('scheduled','present','absent') DEFAULT 'scheduled',

  CONSTRAINT fk_shift FOREIGN KEY (duty_shift_id)
    REFERENCES duty_shifts(id),
  CONSTRAINT fk_shift_doctor FOREIGN KEY (doctor_id)
    REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
