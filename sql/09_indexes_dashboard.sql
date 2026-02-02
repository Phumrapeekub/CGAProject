USE cga_system;

-- encounters: ใช้กรองตามวัน/ช่วงเวลา + distinct patient
CREATE INDEX idx_enc_date_patient ON encounters(encounter_datetime, patient_id);
CREATE INDEX idx_enc_patient_date ON encounters(patient_id, encounter_datetime);
CREATE INDEX idx_enc_status_date ON encounters(status, encounter_datetime);

-- assessment_headers: ใช้ดึงฟอร์มใน encounter
CREATE INDEX idx_assess_enc_form ON assessment_headers(encounter_id, form_code);

-- doctor_notes / diagnoses / referrals / appointments
CREATE INDEX idx_note_enc_signed ON doctor_notes(encounter_id, signed_at);
CREATE INDEX idx_dx_enc ON encounter_diagnoses(encounter_id);
CREATE INDEX idx_ref_enc ON referrals(encounter_id);
CREATE INDEX idx_appt_patient_time ON appointments(patient_id, appointment_datetime);
