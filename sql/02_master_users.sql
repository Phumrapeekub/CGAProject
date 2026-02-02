USE cga_system;

CREATE TABLE roles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  role_code VARCHAR(50) NOT NULL,
  role_name_th VARCHAR(100) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO roles(role_code, role_name_th) VALUES
('admin','ผู้ดูแลระบบ'),
('doctor','แพทย์'),
('nurse','พยาบาล');

USE cga_system;

INSERT INTO users (role_id, username, password_hash, full_name, is_active)
SELECT id, 'doctor', 'PUT_HASH_HERE', 'แพทย์ทดสอบ', 1
FROM roles
WHERE role_code = 'doctor';
USE cga_system;

INSERT INTO users
(role_id, username, password_hash, full_name, is_active)
VALUES
(
  2,              -- 👈 role_id แพทย์
  'doctor',
  'PUT_HASH_HERE',
  'แพทย์ทดสอบ',
  1
);
USE cga_system;

UPDATE users
SET password_hash = 'scrypt:32768:8:1$69xn12NNLlBvWhlD$58b36729a53959c0272aef9aa5572ec87c403abaab0ac057400a074bba21b90c76e2dc56780b137dafc923b71a8c0e8f441e44dc2088aa5dfd87e960e1299bde',
    is_active = 1
WHERE username = 'doctor';

CREATE TABLE users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  role_id BIGINT UNSIGNED NOT NULL,

  username VARCHAR(80) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(255) NOT NULL,

  license_no VARCHAR(80) NULL,
  phone VARCHAR(50) NULL,
  email VARCHAR(120) NULL,

  is_active TINYINT DEFAULT 1,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_username (username),
  KEY idx_role (role_id),

  CONSTRAINT fk_users_role FOREIGN KEY (role_id)
    REFERENCES roles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
USE cga_system;

UPDATE users
SET password_hash = 'scrypt:32768:8:1$69xn12NNLlBvWhlD$58b36729a53959c0272aef9aa5572ec87c403abaab0ac057400a074bba21b90c76e2dc56780b137dafc923b71a8c0e8f441e44dc2088aa5dfd87e960e1299bde'
WHERE username = 'doctor';

USE cga_system;
SELECT id, role_code, role_name_th FROM roles;
SELECT * FROM roles;
DESCRIBE roles;
SELECT u.id, u.username, u.role_id, r.role_code
FROM users u
JOIN roles r ON r.id = u.role_id
WHERE u.username = 'doctor';
SELECT username, role_id, password_hash FROM users WHERE username='doctor';
USE cga_system;
SELECT username, LENGTH(password_hash) AS len
FROM users
WHERE username='doctor';

USE cga_system;

UPDATE users
SET password_hash = 'วางค่า pbkdf2:sha256 ที่ได้มาทั้งก้อนตรงนี้'
WHERE username = 'doctor';
SELECT username, role_id, LEFT(password_hash, 30) AS pfx
FROM users
WHERE username='doctor';
USE cga_system;

UPDATE users
SET password_hash = 'scrypt:32768:8:1$AAA...BBB'
WHERE username = 'doctor';
SELECT username, password_hash FROM users WHERE username='doctor';
