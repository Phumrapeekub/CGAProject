USE cga_system;

LOAD DATA LOCAL INFILE 'C:/Users/User/Downloads/CGA_1000_with_HN.csv'
INTO TABLE import_cga_1000
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(hn, title_name, first_name, last_name, citizen_id_raw, birth_date_raw, age_year, education_level, sex);
SELECT COUNT(*) AS n FROM import_cga_1000;