-- schema.sql
DROP TABLE IF EXISTS members;
DROP TABLE IF EXISTS signins; -- Drop if it exists (for development)

CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    email_opt_in BOOLEAN DEFAULT FALSE,
    sms_opt_in BOOLEAN DEFAULT FALSE,
    last_login TEXT,
    streak INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0
);

CREATE TABLE signins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,  -- ISO 8601 format: YYYY-MM-DD HH:MM:SS
    FOREIGN KEY (member_id) REFERENCES members(id)
);