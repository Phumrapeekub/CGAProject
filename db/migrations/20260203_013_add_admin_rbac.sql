-- 20260203_013_add_admin_rbac.sql
-- Admin RBAC core (roles/permissions) + settings + assessment_versions + password_reset_tokens
-- Target DB: cga_system_dev
-- NOTE:
-- - มีตาราง users และ audit_logs อยู่แล้ว => ไม่สร้างซ้ำ
-- - MySQL 8.x | utf8mb4

USE cga_system_dev;

SET FOREIGN_KEY_CHECKS = 0;

-- =========================================================
-- 1) roles
-- =========================================================
CREATE TABLE IF NOT EXISTS roles (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(50) NOT NULL,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_roles_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 2) permissions
-- =========================================================
CREATE TABLE IF NOT EXISTS permissions (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(120) NOT NULL,
  name VARCHAR(150) NOT NULL,
  description VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_permissions_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 3) user_roles (users <-> roles)
-- users.id = INT  → user_id ต้องเป็น INT
-- =========================================================
CREATE TABLE IF NOT EXISTS user_roles (
  user_id INT NOT NULL,
  role_id INT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, role_id),
  KEY idx_user_roles_role (role_id),
  CONSTRAINT fk_user_roles_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_user_roles_role
    FOREIGN KEY (role_id) REFERENCES roles(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 4) role_permissions (roles <-> permissions)
-- =========================================================
CREATE TABLE IF NOT EXISTS role_permissions (
  role_id INT UNSIGNED NOT NULL,
  permission_id INT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (role_id, permission_id),
  KEY idx_role_permissions_perm (permission_id),
  CONSTRAINT fk_role_permissions_role
    FOREIGN KEY (role_id) REFERENCES roles(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_role_permissions_perm
    FOREIGN KEY (permission_id) REFERENCES permissions(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 5) system_settings (key/value)
-- =========================================================
CREATE TABLE IF NOT EXISTS system_settings (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  setting_key VARCHAR(120) NOT NULL,
  setting_value TEXT NULL,
  description VARCHAR(255) NULL,
  updated_by INT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_system_settings_key (setting_key),
  KEY idx_system_settings_updated_at (updated_at),
  CONSTRAINT fk_system_settings_updated_by
    FOREIGN KEY (updated_by) REFERENCES users(id)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 6) assessment_versions
-- =========================================================
CREATE TABLE IF NOT EXISTS assessment_versions (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  assessment_type VARCHAR(30) NOT NULL,   -- MMSE/TGDS/2Q/8Q/etc
  version VARCHAR(30) NOT NULL,           -- v1, v2, 2026.01
  effective_date DATE NULL,
  description VARCHAR(255) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_by INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_assess_versions (assessment_type, version),
  KEY idx_assess_active (assessment_type, is_active),
  CONSTRAINT fk_assess_versions_created_by
    FOREIGN KEY (created_by) REFERENCES users(id)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 7) password_reset_tokens
-- =========================================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  token_hash CHAR(64) NOT NULL,
  issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  requested_ip VARCHAR(64) NULL,
  user_agent VARCHAR(255) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reset_token_hash (token_hash),
  KEY idx_reset_user (user_id),
  KEY idx_reset_expires (expires_at),
  CONSTRAINT fk_reset_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- Seed: roles
-- =========================================================
INSERT IGNORE INTO roles (code, name, description) VALUES
('admin',  'Administrator', 'Full system access'),
('doctor', 'Doctor',        'Clinical access'),
('nurse',  'Nurse',         'Nursing / assessment access');

-- =========================================================
-- Seed: permissions
-- =========================================================
INSERT IGNORE INTO permissions (code, name, description) VALUES
('manage_users',        'Manage Users',        'Create/Update/Disable users'),
('manage_roles',        'Manage Roles',        'Assign roles/permissions'),
('manage_settings',     'Manage Settings',     'Edit system settings'),
('view_audit_logs',     'View Audit Logs',     'Read audit logs'),

('view_patients',       'View Patients',       'Read patient data'),
('edit_patients',       'Edit Patients',       'Create/update patient data'),
('view_encounters',     'View Encounters',     'Read encounters'),
('edit_encounters',     'Edit Encounters',     'Create/update encounters'),

('view_assessments',    'View Assessments',    'Read CGA assessments'),
('edit_assessments',    'Edit Assessments',    'Create/update CGA assessments'),

('view_appointments',   'View Appointments',   'Read appointments'),
('edit_appointments',   'Edit Appointments',   'Create/update appointments'),
('view_duties',         'View Duties',         'Read duty schedules'),
('edit_duties',         'Edit Duties',         'Create/update duty schedules'),

('export_reports',      'Export Reports',      'Export reports/data');

-- =========================================================
-- Map permissions -> roles
-- =========================================================

-- admin ได้ทุก permission
INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
WHERE r.code = 'admin';

-- doctor
INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
WHERE r.code='doctor'
  AND p.code IN (
    'view_patients','edit_patients',
    'view_encounters','edit_encounters',
    'view_assessments','edit_assessments',
    'view_appointments','edit_appointments',
    'view_duties','edit_duties',
    'export_reports'
  );

-- nurse
INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
WHERE r.code='nurse'
  AND p.code IN (
    'view_patients','edit_patients',
    'view_encounters','edit_encounters',
    'view_assessments','edit_assessments',
    'view_appointments','edit_appointments'
  );

-- =========================================================
-- Seed: assessment_versions
-- =========================================================
INSERT IGNORE INTO assessment_versions
(assessment_type, version, effective_date, description, is_active)
VALUES
('MMSE','v1',NULL,'Default MMSE version',1),
('TGDS','v1',NULL,'Default TGDS version',1),
('2Q',  'v1',NULL,'Default 2Q version',1),
('8Q',  'v1',NULL,'Default 8Q version',1);

-- =========================================================
-- Seed: system_settings
-- =========================================================
INSERT IGNORE INTO system_settings (setting_key, setting_value, description) VALUES
('system_name', 'CGA System', 'System display name'),
('env', 'dev', 'Environment name'),
('password_reset_token_minutes', '30', 'Reset token expiry in minutes');

SET FOREIGN_KEY_CHECKS = 1;
