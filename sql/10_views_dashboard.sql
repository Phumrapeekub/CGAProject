USE cga_system;

-- สรุปจำนวน encounter ต่อวัน + จำนวนคนไข้ไม่ซ้ำต่อวัน
CREATE OR REPLACE VIEW v_daily_stats AS
SELECT
  DATE(e.encounter_datetime) AS stat_date,
  COUNT(*) AS encounters_count,
  COUNT(DISTINCT e.patient_id) AS unique_patients_count
FROM encounters e
GROUP BY DATE(e.encounter_datetime);
