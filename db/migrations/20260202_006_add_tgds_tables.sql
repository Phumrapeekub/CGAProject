USE cga_migration_test;

-- =========================
-- TGDS-15 (Header)
-- =========================
CREATE TABLE IF NOT EXISTS assessment_tgds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cga_id INT NOT NULL,
    total_score INT DEFAULT 0,
    risk_level ENUM('normal','mild','moderate','severe') DEFAULT 'normal',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tgds_cga
        FOREIGN KEY (cga_id)
        REFERENCES cga_headers(id)
        ON DELETE CASCADE
);

-- =========================
-- TGDS-15 (Items)
-- =========================
CREATE TABLE IF NOT EXISTS assessment_tgds_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tgds_id INT NOT NULL,
    question_no INT NOT NULL,     -- 1–15
    answer TINYINT NOT NULL,      -- 0 = No, 1 = Yes
    score INT DEFAULT 0,

    CONSTRAINT fk_tgds_items
        FOREIGN KEY (tgds_id)
        REFERENCES assessment_tgds(id)
        ON DELETE CASCADE
);
