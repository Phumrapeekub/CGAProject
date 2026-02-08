-- =========================================
-- CGA System : Supabase (PostgreSQL) Schema
-- =========================================

-- USERS
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(100),
  role VARCHAR(20) CHECK (role IN ('admin','doctor','nurse')),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PATIENTS
CREATE TABLE IF NOT EXISTS patients (
  id SERIAL PRIMARY KEY,
  hn VARCHAR(20) NOT NULL UNIQUE,
  full_name VARCHAR(100) NOT NULL,
  gender VARCHAR(10) CHECK (gender IN ('male','female','other')),
  birth_date DATE,
  phone VARCHAR(30),
  address TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ENCOUNTERS
CREATE TABLE IF NOT EXISTS encounters (
  id SERIAL PRIMARY KEY,
  patient_id INT NOT NULL REFERENCES patients(id),
  encounter_date DATE NOT NULL,
  encounter_type VARCHAR(20) DEFAULT 'cga' CHECK (encounter_type IN ('cga','followup','other')),
  created_by INT REFERENCES users(id),
  note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- CGA HEADERS
CREATE TABLE IF NOT EXISTS cga_headers (
  id SERIAL PRIMARY KEY,
  encounter_id INT NOT NULL REFERENCES encounters(id),
  assessed_by INT REFERENCES users(id),
  assessment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  risk_level VARCHAR(20),
  is_completed BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ROLES (RBAC)
CREATE TABLE IF NOT EXISTS roles (
  id SERIAL PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- USER_ROLES
CREATE TABLE IF NOT EXISTS user_roles (
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, role_id)
);

-- INITIAL SEED ROLES
INSERT INTO roles (code, name) VALUES 
('admin', 'Administrator'),
('doctor', 'Medical Doctor'),
('nurse', 'Nurse')
ON CONFLICT (code) DO NOTHING;
