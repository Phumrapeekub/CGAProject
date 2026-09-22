-- CGA System Schema for PostgreSQL (Supabase)

-- Enable pgcrypto for password hashing if needed (Flask usually handles this in Python)
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Users & RBAC
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50), -- Legacy column, still used in some routes
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- 2. Master Data
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    hn VARCHAR(20) UNIQUE NOT NULL,
    gcn VARCHAR(20),
    prefix VARCHAR(50),
    full_name VARCHAR(255) NOT NULL,
    gender VARCHAR(10),
    birth_date DATE,
    phone VARCHAR(50),
    line_user_id VARCHAR(100), -- For LineOA Notifications
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Encounters & Sessions
CREATE TABLE IF NOT EXISTS encounters (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
    encounter_date DATE DEFAULT CURRENT_DATE,
    encounter_type VARCHAR(50), -- e.g., 'OPD', 'IPD', 'CGA'
    created_by INTEGER REFERENCES users(id),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assessment_sessions (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cga_headers (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES assessment_sessions(id) ON DELETE CASCADE,
    assessed_by INTEGER REFERENCES users(id),
    assessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Clinical Modules
CREATE TABLE IF NOT EXISTS assessment_scores (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES assessment_sessions(id) ON DELETE CASCADE,
    instrument VARCHAR(50), -- MMSE, TGDS, etc.
    total_score NUMERIC(5,2),
    risk_level VARCHAR(50),
    interpretation TEXT,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
    encounter_id INTEGER REFERENCES encounters(id),
    created_by_doctor INTEGER REFERENCES users(id),
    appt_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    appt_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'scheduled',
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctor_duty_events (
    id SERIAL PRIMARY KEY,
    doctor_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    start_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    end_datetime TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Staging for CSV Import
CREATE TABLE IF NOT EXISTS stg_cga_csv (
  id SERIAL PRIMARY KEY,
  hn VARCHAR(20),
  prefix VARCHAR(20),
  first_name VARCHAR(100),
  last_name VARCHAR(100),
  citizen_id TEXT,
  dob_text VARCHAR(50),
  age INT,
  education VARCHAR(100),
  sex VARCHAR(20),
  house_no VARCHAR(30),
  moo VARCHAR(30),
  subdistrict VARCHAR(100),
  district VARCHAR(100),
  province VARCHAR(100),
  full_address TEXT,
  caregiver_name VARCHAR(150),
  phone VARCHAR(50),
  has_comorbidity VARCHAR(20),
  comorbidity_detail TEXT,
  mmse_score INT,
  mmse_result VARCHAR(100),
  tgds_score INT,
  tgds_result VARCHAR(100),
  q8_score INT,
  suicide_risk_level VARCHAR(150),
  hearing_left_result VARCHAR(100),
  hearing_left_detail TEXT,
  hearing_right_result VARCHAR(100),
  hearing_right_detail TEXT,
  vision_right_snellen VARCHAR(50),
  vision_left_snellen VARCHAR(50),
  incontinence VARCHAR(100),
  sleep_problem VARCHAR(100),
  assessed_date_text VARCHAR(50)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_patients_hn ON patients(hn);
CREATE INDEX IF NOT EXISTS idx_encounters_patient_id ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_date ON encounters(encounter_date);
CREATE INDEX IF NOT EXISTS idx_stg_hn ON stg_cga_csv(hn);

-- Seed Basic Roles
INSERT INTO roles (code, name) VALUES ('admin', 'Administrator') ON CONFLICT (code) DO NOTHING;
INSERT INTO roles (code, name) VALUES ('doctor', 'Doctor') ON CONFLICT (code) DO NOTHING;
INSERT INTO roles (code, name) VALUES ('nurse', 'Nurse') ON CONFLICT (code) DO NOTHING;

-- Seed a default doctor (password: doctor123)
-- Hash generated via werkzeug.security.generate_password_hash
INSERT INTO users (username, password_hash, full_name, role, is_active)
VALUES ('doctor01', 'scrypt:32768:8:1$7f9e8f...$8a...', 'นพ. ใจดี มีสุข', 'doctor', true)
ON CONFLICT (username) DO NOTHING;

-- Link doctor role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u, roles r WHERE u.username='doctor01' AND r.code='doctor'
ON CONFLICT DO NOTHING;
