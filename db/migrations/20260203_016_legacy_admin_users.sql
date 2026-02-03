-- =========================================================
-- 20260203_016_legacy_admin_users.sql
-- Purpose:
--   - Keep admin_users as legacy
--   - Migrate / link legacy admin_users into central users table
--   - SAFE TO RE-RUN (idempotent)
--
-- Target DB: cga_system_dev
--
-- Assumptions:
--   - users table exists
--   - admin_users table exists (legacy)
--   - users.username is UNIQUE
-- =========================================================

USE cga_system_dev;

-- ---------------------------------------------------------
-- 1) INSERT legacy admin_users that do NOT exist in users
-- ---------------------------------------------------------
INSERT INTO users (
    username,
    password_hash,
    legacy_provider,
    legacy_user_id,
    is_active,
    created_at
)
SELECT
    au.username,
    au.password_hash,
    'admin_users'        AS legacy_provider,
    au.id                AS legacy_user_id,
    au.is_active,
    au.created_at
FROM admin_users au
LEFT JOIN users u
       ON u.username = au.username
WHERE u.id IS NULL;

-- ---------------------------------------------------------
-- 2) LINK legacy info for users that already exist
--    (e.g. seeded admin)
-- ---------------------------------------------------------
UPDATE users u
JOIN admin_users au
  ON au.username = u.username
SET
  u.legacy_provider = COALESCE(u.legacy_provider, 'admin_users'),
  u.legacy_user_id  = COALESCE(u.legacy_user_id, au.id)
WHERE u.legacy_provider IS NULL;

-- ---------------------------------------------------------
-- 3) VERIFY (optional, safe)
-- ---------------------------------------------------------
SELECT
    u.id,
    u.username,
    u.legacy_provider,
    u.legacy_user_id,
    u.created_at
FROM users u
WHERE u.legacy_provider = 'admin_users'
ORDER BY u.id;
