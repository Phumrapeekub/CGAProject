-- =========================================
-- CGA System : Baseline Schema
-- Users / Patients / Encounters
-- =========================================

CREATE DATABASE IF NOT EXISTS cga_system_dev
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cga_system_dev;

-- =========================================
-- 1) USERS
-- actor: admin / doctor / nurse
-- =========================================
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(100),
  role ENUM('admin','doctor','nurse') NOT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================
-- 2) PATIENTS
-- ตัวตนผู้ป่วย (1 คน มีหลาย encounter)
-- =========================================
CREATE TABLE patients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hn VARCHAR(20) NOT NULL UNIQUE,
  full_name VARCHAR(100) NOT NULL,
  gender ENUM('male','female','other'),
  birth_date DATE,
  phone VARCHAR(30),
  address TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================
-- 3) ENCOUNTERS  ⭐ แกนกลางระบบ
-- การมารับบริการ / การประเมินแต่ละครั้ง
-- =========================================
CREATE TABLE encounters (
  id INT AUTO_INCREMENT PRIMARY KEY,

  patient_id INT NOT NULL,
  encounter_date DATE NOT NULL,

  encounter_type ENUM('cga','followup','other') DEFAULT 'cga',
  created_by INT, -- พยาบาล/ผู้สร้าง encounter

  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (patient_id) REFERENCES patients(id),
  FOREIGN KEY (created_by) REFERENCES users(id)
);
