-- CGA System - Baseline Schema (safe, re-runnable)
-- Generated from mysqldump structure and normalized for team use
-- Date: 2026-02-01

CREATE DATABASE IF NOT EXISTS `cga_system`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `cga_system`;

-- =========================
-- 1) Core tables (no FK deps)
-- =========================

CREATE TABLE IF NOT EXISTS `patient_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `hn` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `gcn` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `surname` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `age` int DEFAULT NULL,
  `gender` enum('ชาย','หญิง') COLLATE utf8mb4_unicode_ci DEFAULT 'ชาย',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `disease` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `risk_level` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `date_assessed` datetime DEFAULT CURRENT_TIMESTAMP,
  `mmse` int DEFAULT NULL,
  `tgds` int DEFAULT NULL,
  `sra` int DEFAULT NULL,
  `address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `marry` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `live` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `smoke` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `alcohol` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `height_cm` int DEFAULT NULL,
  `weight_kg` int DEFAULT NULL,
  `waist_cm` int DEFAULT NULL,
  `birthdate` date DEFAULT NULL,
  `num_people` int DEFAULT NULL,
  `hearing_left` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hearing_right` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `vision_snellen` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL COMMENT 'ชื่อผู้ใช้สำหรับ login',
  `password_hash` varchar(255) NOT NULL COMMENT 'รหัสผ่านแบบ hash',
  `full_name` varchar(120) NOT NULL COMMENT 'ชื่อ-นามสกุลจริง',
  `role` enum('admin','nurse','doctor') NOT NULL DEFAULT 'nurse' COMMENT 'สิทธิ์ผู้ใช้งาน',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT 'เปิด/ปิดการใช้งาน',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- 2) Assessment session system (FK deps)
-- =========================

CREATE TABLE IF NOT EXISTS `assessment_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `form_code` enum('MMSE','TGDS','Q8','SRA') NOT NULL,
  `status` enum('final','corrected') NOT NULL DEFAULT 'final',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by_user_id` int DEFAULT NULL,
  `note` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_patient_form_time` (`patient_id`,`form_code`,`created_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_answers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` int NOT NULL,
  `question_code` varchar(40) NOT NULL,
  `answer_value` varchar(255) DEFAULT NULL,
  `answer_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_session_question` (`session_id`,`question_code`),
  KEY `idx_session` (`session_id`),
  CONSTRAINT `fk_answers_session`
    FOREIGN KEY (`session_id`) REFERENCES `assessment_sessions` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_scores` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` int NOT NULL,
  `total_score` int DEFAULT NULL,
  `computed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `session_id` (`session_id`),
  CONSTRAINT `fk_scores_session`
    FOREIGN KEY (`session_id`) REFERENCES `assessment_sessions` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_revisions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `form_code` enum('MMSE','TGDS','Q8','SRA') NOT NULL,
  `base_session_id` int NOT NULL,
  `new_session_id` int NOT NULL,
  `corrected_by_user_id` int DEFAULT NULL,
  `corrected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `reason` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_patient_form` (`patient_id`,`form_code`),
  KEY `fk_rev_base` (`base_session_id`),
  KEY `fk_rev_new` (`new_session_id`),
  CONSTRAINT `fk_rev_base` FOREIGN KEY (`base_session_id`) REFERENCES `assessment_sessions` (`id`),
  CONSTRAINT `fk_rev_new`  FOREIGN KEY (`new_session_id`)  REFERENCES `assessment_sessions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- 3) CGA assessment summary
-- =========================

CREATE TABLE IF NOT EXISTS `assessments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `assess_date` datetime DEFAULT CURRENT_TIMESTAMP,
  `assessor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mmse` int DEFAULT NULL,
  `depression` int DEFAULT NULL,
  `ai_summary` text COLLATE utf8mb4_unicode_ci,
  `doctor_notes` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  KEY `patient_id` (`patient_id`),
  CONSTRAINT `assessments_ibfk_1`
    FOREIGN KEY (`patient_id`) REFERENCES `patient_history` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- 4) Form-specific tables
-- (kept as-is: no FK in your dump)
-- =========================

CREATE TABLE IF NOT EXISTS `assessment_mmse` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `edu` tinyint unsigned DEFAULT NULL,
  `q1_1` tinyint DEFAULT NULL,
  `q1_2` tinyint DEFAULT NULL,
  `q1_3` tinyint DEFAULT NULL,
  `q1_4` tinyint DEFAULT NULL,
  `q1_5` tinyint DEFAULT NULL,
  `q2_1` tinyint DEFAULT NULL,
  `q2_2` tinyint DEFAULT NULL,
  `q2_3` tinyint DEFAULT NULL,
  `q2_4` tinyint DEFAULT NULL,
  `q2_5` tinyint DEFAULT NULL,
  `q3` tinyint DEFAULT NULL,
  `q4_1` tinyint DEFAULT NULL,
  `q4_2` tinyint DEFAULT NULL,
  `q5` tinyint DEFAULT NULL,
  `q6` tinyint DEFAULT NULL,
  `q7` tinyint DEFAULT NULL,
  `q8` tinyint DEFAULT NULL,
  `q9` tinyint DEFAULT NULL,
  `q10` tinyint DEFAULT NULL,
  `q11` tinyint DEFAULT NULL,
  `total_score` tinyint DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_sra` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `q1` tinyint DEFAULT NULL,
  `q2` tinyint DEFAULT NULL,
  `q3` tinyint DEFAULT NULL,
  `q4` tinyint DEFAULT NULL,
  `q5` tinyint DEFAULT NULL,
  `q6` tinyint DEFAULT NULL,
  `q7` tinyint DEFAULT NULL,
  `q8` tinyint DEFAULT NULL,
  `total_score` tinyint DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_tgds` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` int NOT NULL,
  `q1` tinyint DEFAULT NULL,
  `q2` tinyint DEFAULT NULL,
  `q3` tinyint DEFAULT NULL,
  `q4` tinyint DEFAULT NULL,
  `q5` tinyint DEFAULT NULL,
  `q6` tinyint DEFAULT NULL,
  `q7` tinyint DEFAULT NULL,
  `q8` tinyint DEFAULT NULL,
  `q9` tinyint DEFAULT NULL,
  `q10` tinyint DEFAULT NULL,
  `q11` tinyint DEFAULT NULL,
  `q12` tinyint DEFAULT NULL,
  `q13` tinyint DEFAULT NULL,
  `q14` tinyint DEFAULT NULL,
  `q15` tinyint DEFAULT NULL,
  `total_score` tinyint DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `assessment_notes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `hn` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `gcn` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- 5) Logs
-- =========================

CREATE TABLE IF NOT EXISTS `ai_chat_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `hn` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gcn` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `patient_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `page` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `ai_reply` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `audit_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `action` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `hn` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gcn` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `detail` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- 6) Migration tracking (for team workflow)
-- =========================

CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) NOT NULL,
  `applied_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_schema_migrations_filename` (`filename`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
