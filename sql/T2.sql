CREATE DATABASE cga_system
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE cga_system;
CREATE TABLE users (
  user_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','nurse','doctor') NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  is_active TINYINT DEFAULT 1
);

CREATE TABLE patients (
  hn VARCHAR(20) PRIMARY KEY,
  prefix VARCHAR(20),
  first_name VARCHAR(100),
  last_name VARCHAR(100),
  dob DATE,
  sex VARCHAR(20)
);

CREATE TABLE encounters (
  encounter_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  hn VARCHAR(20),
  visit_datetime DATETIME,
  created_by BIGINT,
  status VARCHAR(20),
  FOREIGN KEY (hn) REFERENCES patients(hn)
);

CREATE TABLE cga_results (
  cga_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  encounter_id BIGINT UNIQUE,
  mmse_score INT,
  tgds_score INT,
  q8_score INT,
  FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
INSERT INTO users (username, password_hash, role, full_name)
VALUES ('doctor', 'TEMP_HASH', 'doctor', 'แพทย์ทดสอบ');

INSERT INTO patients (hn, prefix, first_name, last_name, dob, sex)
VALUES ('HN001', 'นาย', 'สมชาย', 'ใจดี', '1955-01-01', 'ชาย');

INSERT INTO encounters (hn, visit_datetime, status)
VALUES ('HN001', NOW(), 'assessed');

INSERT INTO cga_results (encounter_id, mmse_score, tgds_score, q8_score)
VALUES (1, 23, 3, 0);
