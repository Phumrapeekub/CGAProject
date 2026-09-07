-- Migration: Add extra info fields to users table for doctors/nurses
-- Date: 2026-02-17

USE cga_system_dev;

ALTER TABLE users 
ADD COLUMN specialization VARCHAR(100) NULL AFTER full_name,
ADD COLUMN phone VARCHAR(20) NULL AFTER specialization,
ADD COLUMN email VARCHAR(100) NULL AFTER phone,
ADD COLUMN bio TEXT NULL AFTER email,
ADD COLUMN education TEXT NULL AFTER bio;
