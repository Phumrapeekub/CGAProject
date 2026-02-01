USE cga_data;

CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) UNIQUE,
  password_hash VARCHAR(255),
  role ENUM('admin','nurse','doctor') NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  license_no VARCHAR(50),
  phone VARCHAR(50),
  is_active TINYINT DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS patients (
  hn VARCHAR(20) PRIMARY KEY,
  citizen_id VARCHAR(13),
  prefix VARCHAR(20),
  first_name VARCHAR(100),
  last_name VARCHAR(100),
  dob DATE,
  sex VARCHAR(20),
  education VARCHAR(100),
  phone VARCHAR(50),
  address TEXT,
  caregiver_name VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS encounters (
  encounter_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  hn VARCHAR(20) NOT NULL,
  visit_datetime DATETIME NOT NULL,
  created_by BIGINT,
  status ENUM('waiting','assessed','doctor_seen','finished') DEFAULT 'waiting',
  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_visit_date (visit_datetime),
  INDEX idx_hn_date (hn, visit_datetime),

  CONSTRAINT fk_encounter_patient FOREIGN KEY (hn) REFERENCES patients(hn),
  CONSTRAINT fk_encounter_user FOREIGN KEY (created_by) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cga_results (
  cga_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT NOT NULL,
  assessed_by BIGINT,
  assessed_date DATE,

  mmse_score INT,
  mmse_result VARCHAR(100),

  tgds_score INT,
  tgds_result VARCHAR(100),

  q8_score INT,
  q8_risk VARCHAR(100),

  hearing_left VARCHAR(50),
  hearing_right VARCHAR(50),
  vision_left VARCHAR(50),
  vision_right VARCHAR(50),

  incontinence VARCHAR(100),
  sleep_problem VARCHAR(100),
  comorbidity_detail TEXT,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uq_encounter (encounter_id),
  CONSTRAINT fk_cga_encounter FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id),
  CONSTRAINT fk_cga_nurse FOREIGN KEY (assessed_by) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS doctor_notes (
  note_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT NOT NULL,
  doctor_id BIGINT NOT NULL,
  diagnosis TEXT,
  treatment_plan TEXT,
  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_note_encounter FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id),
  CONSTRAINT fk_note_doctor FOREIGN KEY (doctor_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS referrals (
  referral_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT NOT NULL,
  from_doctor_id BIGINT NOT NULL,
  to_department VARCHAR(150),
  to_hospital VARCHAR(150),
  reason TEXT,
  status ENUM('sent','accepted','rejected','completed') DEFAULT 'sent',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_ref_encounter FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id),
  CONSTRAINT fk_ref_doctor FOREIGN KEY (from_doctor_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS appointments (
  appointment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  hn VARCHAR(20) NOT NULL,
  doctor_id BIGINT,
  appointment_datetime DATETIME NOT NULL,
  purpose VARCHAR(200),
  status ENUM('scheduled','checked_in','done','cancelled','no_show') DEFAULT 'scheduled',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_appt_date (appointment_datetime),

  CONSTRAINT fk_appt_patient FOREIGN KEY (hn) REFERENCES patients(hn),
  CONSTRAINT fk_appt_doctor FOREIGN KEY (doctor_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS doctor_shifts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  doctor_id INT NOT NULL,
  shift_date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  shift_type VARCHAR(20) NOT NULL DEFAULT 'day',   -- day/evening/night/oncall
  location VARCHAR(120) DEFAULT NULL,
  note TEXT DEFAULT NULL,                          -- โน้ตส่วนตัวของหมอ
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_doc_date (doctor_id, shift_date)
);
