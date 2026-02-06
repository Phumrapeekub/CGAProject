-- db/seeds/001_users_demo.sql

INSERT INTO users (username, password_hash, full_name, role, is_active)
VALUES
('admin_demo',
 'scrypt:32768:8:1$jNM8Lh5u6jDKgoui$336e6516e78c8ffaf7a1010387c0ce94ff0c3c8eb4d6aefcfa4449f3024de0610a6827332ac210fe1ba6698303f75fcb42385a82f468c9a0e944ff1c525636dd',
 'Admin Demo', 'admin', 1),
('doctor_demo',
 'scrypt:32768:8:1$vH5CSxb0sAv1nXNw$97325367855dadd798ec50ecce6bf63314024dde35228380d43f23e6ffc300cd737e26536ec16460b8653a5e37954de61aa3872f8ccbd2f485931e8b5ccfb54c',
 'Doctor Demo', 'doctor', 1),
('nurse_demo',
 'scrypt:32768:8:1$rZQ1UHq8CKClZXOr$0566706ce169ee3ce3e102ee37283651249ae1f150c0fddbdd20f94d27efc24818ad3647507729c3f0408d3bf7bb87613203fa0e23ede051673d44f754dd0fac',
 'Nurse Demo', 'nurse', 1)
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  full_name     = VALUES(full_name),
  role          = VALUES(role),
  is_active     = VALUES(is_active);
