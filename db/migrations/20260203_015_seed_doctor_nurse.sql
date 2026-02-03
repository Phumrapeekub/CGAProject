-- 20260203_015_seed_doctor_nurse.sql
-- Seed initial doctor/nurse users + assign roles (safe to re-run)
-- Target DB: cga_system_dev
-- Assumes: users, roles, user_roles already exist (from 013/014)

USE cga_system_dev;

-- =========================
-- CONFIG (แก้ตรงนี้)
-- =========================
SET @DOC_USERNAME = 'doctor1';
SET @DOC_PASSWORD_HASH = 'scrypt:32768:8:1$yRqWiOeCEnbmPQtW$34acf42883e75640d1ace468d3f092a0599ec98a0f0a0d5eef375f66b43de97cb5b7071b1316b9460610cb36102ad12ec63c52267d67996890135a92c3795c63';
SET @DOC_IS_ACTIVE = 1;

SET @NUR_USERNAME = 'nurse1';
SET @NUR_PASSWORD_HASH = 'scrypt:32768:8:1$LylJiwjhu86iXOwA$f0da8c14a187564042984911ca1757e89c8e5644ec71be5eb21a9f95bc958405aed38ab0735f8ca06f5932a9c1cb3e062656e29bf006ed5e59ed9a68708a35b6';
SET @NUR_IS_ACTIVE = 1;

-- =========================
-- 1) Insert DOCTOR user if not exists
-- =========================
INSERT INTO users (username, password_hash, is_active, created_at)
SELECT
  @DOC_USERNAME COLLATE utf8mb4_unicode_ci,
  @DOC_PASSWORD_HASH,
  @DOC_IS_ACTIVE,
  NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM users
  WHERE username = @DOC_USERNAME COLLATE utf8mb4_unicode_ci
);

-- =========================
-- 2) Insert NURSE user if not exists
-- =========================
INSERT INTO users (username, password_hash, is_active, created_at)
SELECT
  @NUR_USERNAME COLLATE utf8mb4_unicode_ci,
  @NUR_PASSWORD_HASH,
  @NUR_IS_ACTIVE,
  NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM users
  WHERE username = @NUR_USERNAME COLLATE utf8mb4_unicode_ci
);

-- =========================
-- 3) Assign DOCTOR role
-- =========================
INSERT IGNORE INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
JOIN roles r ON r.code='doctor'
WHERE u.username = @DOC_USERNAME COLLATE utf8mb4_unicode_ci;

-- =========================
-- 4) Assign NURSE role
-- =========================
INSERT IGNORE INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
JOIN roles r ON r.code='nurse'
WHERE u.username = @NUR_USERNAME COLLATE utf8mb4_unicode_ci;

-- =========================
-- 5) Quick verify (optional)
-- =========================
SELECT u.username, r.code AS role
FROM users u
JOIN user_roles ur ON ur.user_id=u.id
JOIN roles r ON r.id=ur.role_id
WHERE u.username IN (@DOC_USERNAME, @NUR_USERNAME)
ORDER BY u.username, r.code;
