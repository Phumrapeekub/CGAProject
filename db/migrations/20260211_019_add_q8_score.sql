-- เพิ่มคอลัมน์คะแนน 8Q ในตาราง cga_records
ALTER TABLE cga_records ADD COLUMN IF NOT EXISTS q8_score INTEGER DEFAULT 0;
