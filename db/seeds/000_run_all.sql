-- db/seeds/000_run_all.sql
-- Run seeds in correct order (idempotent)

SOURCE db/seeds/001_users_demo.sql;
SOURCE db/seeds/002_patients_demo.sql;
SOURCE db/seeds/003_encounters_demo.sql;
SOURCE db/seeds/004_assessment_sessions_demo.sql;
SOURCE db/seeds/005_cga_headers_demo.sql;
