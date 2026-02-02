USE cga_system;

DROP TABLE IF EXISTS import_cga_1000;

CREATE TABLE import_cga_1000 (
  hn VARCHAR(32),
  title_name VARCHAR(20),
  first_name VARCHAR(120),
  last_name VARCHAR(120),
  citizen_id_raw VARCHAR(50),
  birth_date_raw VARCHAR(20),
  age_year INT,
  education_level VARCHAR(50),
  sex VARCHAR(20),

  house_no VARCHAR(50),
  moo VARCHAR(50),
  tambon VARCHAR(120),
  amphoe VARCHAR(120),
  province VARCHAR(120),
  address_text VARCHAR(500),

  caregiver_name VARCHAR(255),
  phone VARCHAR(50),

  chronic_has VARCHAR(20),
  chronic_detail TEXT,

  mmse_score DECIMAL(10,2),
  mmse_result VARCHAR(255),

  tgds_score DECIMAL(10,2),
  tgds_result VARCHAR(255),

  q8_score DECIMAL(10,2),
  q8_risk_level VARCHAR(255),

  hearing_left_result VARCHAR(50),
  hearing_left_note VARCHAR(255),
  hearing_right_result VARCHAR(50),
  hearing_right_note VARCHAR(255),

  vision_right_snellen VARCHAR(50),
  vision_left_snellen VARCHAR(50),

  urinary_incontinence VARCHAR(50),
  sleep_problem VARCHAR(255),

  assess_date_raw VARCHAR(20)   -- YYYY-MM-DD
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
