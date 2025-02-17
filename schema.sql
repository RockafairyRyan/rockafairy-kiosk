-- schema.sql
DROP TABLE IF EXISTS members;
DROP TABLE IF EXISTS signins;
DROP TABLE IF EXISTS ruby_adjustments;
DROP TABLE IF EXISTS rewards;       -- NEW
DROP TABLE IF EXISTS redemptions;   -- NEW

CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    email_opt_in BOOLEAN DEFAULT FALSE,
    sms_opt_in BOOLEAN DEFAULT FALSE,
    last_login TEXT,
    streak INTEGER DEFAULT 0,
    rubies INTEGER DEFAULT 0,
    signup_date TEXT DEFAULT (date('now'))
);

CREATE TABLE signins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (member_id) REFERENCES members(id)
);

CREATE TABLE ruby_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    admin_user TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (member_id) REFERENCES members(id)
);

CREATE TABLE rewards (  -- NEW TABLE
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,  -- Allow NULL descriptions
    ruby_cost INTEGER NOT NULL,
    quantity_available INTEGER,  -- Allow NULL for unlimited
    image_path TEXT,  -- Allow NULL if no image
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE redemptions (  -- NEW TABLE
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    reward_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    admin_user TEXT, -- Allow NULL if self-service
    FOREIGN KEY (member_id) REFERENCES members(id),
    FOREIGN KEY (reward_id) REFERENCES rewards(id)
);