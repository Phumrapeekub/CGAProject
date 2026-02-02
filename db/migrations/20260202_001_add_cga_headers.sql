-- CGA Header (1 encounter = 1 CGA)

CREATE TABLE cga_headers (
  id INT AUTO_INCREMENT PRIMARY KEY,

  encounter_id INT NOT NULL,
  assessed_by INT,                 -- พยาบาลที่ประเมิน
  assessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  overall_risk ENUM('low','medium','high'),
  note TEXT,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uq_cga_per_encounter (encounter_id),
  FOREIGN KEY (encounter_id) REFERENCES encounters(id),
  FOREIGN KEY (assessed_by) REFERENCES users(id)
);
