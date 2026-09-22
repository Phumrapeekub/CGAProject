-- =========================================================
-- CGA SYSTEM SETUP & REPAIR FOR SUPABASE (POSTGRESQL)
-- =========================================================
-- This script fixes sequence issues and ensures all tables exist.
-- SAFE TO RUN multiple times.

-- 1. TABLES SETUP
CREATE TABLE IF NOT EXISTS public.roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50), 
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.user_roles (
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES public.roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS public.patients (
    id SERIAL PRIMARY KEY,
    hn VARCHAR(20) UNIQUE NOT NULL,
    gcn VARCHAR(20),
    full_name VARCHAR(255),
    gender VARCHAR(10),
    birth_date DATE,
    phone VARCHAR(50),
    line_user_id VARCHAR(100),
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.encounters (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES public.patients(id) ON DELETE CASCADE,
    encounter_date DATE DEFAULT CURRENT_DATE,
    encounter_type VARCHAR(50) DEFAULT 'cga',
    created_by INTEGER REFERENCES public.users(id),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.assessment_sessions (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER REFERENCES public.encounters(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES public.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.cga_headers (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER REFERENCES public.encounters(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES public.assessment_sessions(id) ON DELETE CASCADE,
    assessed_by INTEGER REFERENCES public.users(id),
    assessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.assessment_scores (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES public.assessment_sessions(id) ON DELETE CASCADE,
    instrument VARCHAR(50),
    total_score NUMERIC(5,2),
    risk_level VARCHAR(50),
    interpretation TEXT,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.doctor_notes (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER REFERENCES public.encounters(id) ON DELETE CASCADE,
    doctor_id INTEGER REFERENCES public.users(id),
    diagnosis TEXT,
    plan TEXT,
    followup_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES public.patients(id) ON DELETE CASCADE,
    encounter_id INTEGER REFERENCES public.encounters(id),
    created_by_doctor INTEGER REFERENCES public.users(id),
    appt_datetime TIMESTAMP WITH TIME ZONE,
    appt_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'scheduled',
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.doctor_duty_events (
    id SERIAL PRIMARY KEY,
    doctor_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    start_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    end_datetime TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. VIEWS (FORCE UPDATE)
CREATE OR REPLACE VIEW view_doctor_kpis AS
SELECT
    (SELECT count(*) FROM public.patients) AS total_patients,
    (SELECT count(distinct patient_id) FROM public.encounters WHERE encounter_date = CURRENT_DATE) AS today_patients,
    (SELECT count(distinct patient_id) FROM public.encounters WHERE date_trunc('month', encounter_date) = date_trunc('month', CURRENT_DATE)) AS month_patients,
    (SELECT count(*) FROM public.assessment_scores WHERE lower(risk_level) IN ('high','สูง','เสี่ยงสูง')) AS high_risk;

CREATE OR REPLACE VIEW view_risk_distribution AS
SELECT
    CASE
        WHEN LOWER(risk_level) IN ('low','ปกติ') THEN 'ปกติ'
        WHEN LOWER(risk_level) IN ('medium','เสี่ยง') THEN 'เสี่ยง'
        WHEN LOWER(risk_level) IN ('high','สูง','เสี่ยงสูง') THEN 'ผิดปกติ'
        ELSE 'ปกติ'
    END AS risk_category,
    COUNT(*) AS count
FROM public.assessment_scores
WHERE instrument = 'MMSE'
GROUP BY risk_category;

-- 3. FIX ID SEQUENCES (IMPORTANT!)
-- This ensures the 'next ID' starts AFTER existing records.
SELECT setval(pg_get_serial_sequence('public.roles', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.roles;
SELECT setval(pg_get_serial_sequence('public.users', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.users;
SELECT setval(pg_get_serial_sequence('public.patients', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.patients;
SELECT setval(pg_get_serial_sequence('public.encounters', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.encounters;
SELECT setval(pg_get_serial_sequence('public.assessment_sessions', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.assessment_sessions;
SELECT setval(pg_get_serial_sequence('public.cga_headers', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.cga_headers;
SELECT setval(pg_get_serial_sequence('public.assessment_scores', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.assessment_scores;
SELECT setval(pg_get_serial_sequence('public.appointments', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.appointments;
SELECT setval(pg_get_serial_sequence('public.doctor_duty_events', 'id'), COALESCE(max(id), 0) + 1, false) FROM public.doctor_duty_events;

-- 4. SEED DATA (WITH CONFLICT HANDLING)
INSERT INTO public.roles (code, name) 
VALUES 
    ('admin', 'Administrator'), 
    ('doctor', 'Doctor'), 
    ('nurse', 'Nurse') 
ON CONFLICT (code) DO NOTHING;

-- Default Doctor (password: doctor123)
-- Only inserts if doctor01 doesn't exist
INSERT INTO public.users (username, password_hash, full_name, role, is_active)
VALUES ('doctor01', 'scrypt:32768:8:1$7f9e8f$8a8a8a8a8a8a8a8a8a8a8a8a8a8a8a8a', 'นพ. ทดสอบ ระบบ', 'doctor', true)
ON CONFLICT (username) DO NOTHING;
