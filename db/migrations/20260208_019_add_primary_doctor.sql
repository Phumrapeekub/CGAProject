-- Add primary_doctor_id to patients table
-- To link a patient to a responsible doctor

ALTER TABLE patients
ADD COLUMN IF NOT EXISTS primary_doctor_id INT NULL REFERENCES users(id);

CREATE INDEX IF NOT EXISTS idx_patients_primary_doctor ON patients(primary_doctor_id);
