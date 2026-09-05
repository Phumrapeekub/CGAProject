-- 20260206_017_add_doctor_duty_events.sql
-- ตารางเวรแพทย์ สำหรับ calendar (events) + note

CREATE TABLE IF NOT EXISTS doctor_duty_events (
    id INT AUTO_INCREMENT PRIMARY KEY,

    doctor_id INT NOT NULL,

    title VARCHAR(255) NOT NULL DEFAULT 'ตารางเข้าเวร',
    note TEXT NULL,

    start_datetime DATETIME NOT NULL,
    end_datetime DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_doctor_start (doctor_id, start_datetime),
    CONSTRAINT fk_doctor_duty_events_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
