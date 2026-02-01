USE cga_system;

CREATE TABLE patients (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

  hn VARCHAR(32),
  gcn VARCHAR(32),

  title_name ENUM('นาย','นาง','นางสาว','อื่นๆ'),
  first_name VARCHAR(120) NOT NULL,
  last_name VARCHAR(120) NOT NULL,
  sex ENUM('ชาย','หญิง','อื่นๆ','ไม่ระบุ'),

  birth_date DATE,
  age_year INT,
  citizen_id VARCHAR(13),

  phone VARCHAR(50),
  address_text VARCHAR(500),

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  UNIQUE KEY uq_citizen (citizen_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
