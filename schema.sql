-- schema.sql
DROP TABLE IF EXISTS members;
DROP TABLE IF EXISTS signins;

CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    email_opt_in BOOLEAN DEFAULT FALSE,
    sms_opt_in BOOLEAN DEFAULT FALSE,
    last_login TEXT,
    streak INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0,
    signup_date TEXT DEFAULT (date('now'))
);

CREATE TABLE signins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (member_id) REFERENCES members(id)
);