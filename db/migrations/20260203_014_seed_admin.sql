USE cga_system_dev;

SET @ADMIN_USERNAME = 'admin';
SET @ADMIN_PASSWORD_HASH = '<PUT_HASH_HERE>';
SET @ADMIN_IS_ACTIVE = 1;

-- Insert admin user if not exists (fix collation -> unicode_ci)
INSERT INTO users (username, password_hash, is_active, created_at)
SELECT
  @ADMIN_USERNAME COLLATE utf8mb4_unicode_ci,
  @ADMIN_PASSWORD_HASH,
  @ADMIN_IS_ACTIVE,
  NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM users
  WHERE username = @ADMIN_USERNAME COLLATE utf8mb4_unicode_ci
);

-- Assign admin role (fix collation -> unicode_ci)
INSERT IGNORE INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
JOIN roles r ON r.code='admin'
WHERE u.username = @ADMIN_USERNAME COLLATE utf8mb4_unicode_ci;
