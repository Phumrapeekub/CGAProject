-- เพิ่มคอลัมน์ปริมาณการดื่มแอลกอฮอล์ในตาราง cga_records
-- (รันทั้งใน MySQL Local และ Supabase Cloud)

ALTER TABLE cga_records ADD COLUMN IF NOT EXISTS alcohol_amount VARCHAR(50);
