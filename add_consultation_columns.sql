-- เพิ่มคอลัมน์รายละเอียดในตาราง consultations บน Supabase
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS age INTEGER;
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS cognition_status TEXT;
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS health_behavior TEXT;
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS incontinence TEXT;
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS sleep_problem TEXT;
ALTER TABLE consultations ADD COLUMN IF NOT EXISTS depression_2q TEXT;
