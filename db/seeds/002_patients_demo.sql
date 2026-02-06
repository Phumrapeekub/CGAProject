-- db/seeds/002_patients_demo.sql

INSERT INTO patients (hn, gcn, full_name, gender)
VALUES
('HN001', 'GCN-P-001', 'สมชาย ใจดี',   'male'),
('HN002', 'GCN-P-002', 'สมหญิง สุขใจ',  'female'),
('HN003', NULL,        'นายทดสอบ เดโม', 'other')
ON DUPLICATE KEY UPDATE
  gcn       = VALUES(gcn),
  full_name = VALUES(full_name),
  gender    = VALUES(gender);
