-- Add assigned_doctor_id to encounters table
-- To link a patient visit to a specific doctor

ALTER TABLE encounters
ADD COLUMN IF NOT EXISTS assigned_doctor_id INT NULL;

ALTER TABLE encounters
ADD CONSTRAINT fk_encounters_doctor
FOREIGN KEY (assigned_doctor_id) REFERENCES users(id)
ON DELETE SET NULL;

CREATE INDEX idx_encounters_doctor ON encounters(assigned_doctor_id);
