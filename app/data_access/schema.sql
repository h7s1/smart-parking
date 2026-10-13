-- Smart Parking System: database schema
-- Built from the Personal Data Map (v1). Each table stores only the data items
-- the map marks as necessary; full names, phone numbers and GPS locations are
-- never stored (PR-02).
--
-- Conventions
--   * Every ID is a random UUID (version 4) stored as text (SR-07).
--   * Every time is stored in UTC as 'YYYY-MM-DD HH:MM:SS', so text comparison
--     gives the correct time order.

PRAGMA foreign_keys = ON;

-- Users: drivers, admins and support agents.
CREATE TABLE IF NOT EXISTS users (
    id             TEXT PRIMARY KEY,                -- random UUID (SR-07)
    email_enc      TEXT NOT NULL,                   -- AES-256-GCM encrypted email (PR-03)
    password_hash  TEXT NOT NULL,                   -- bcrypt hash, cost >= 10 (SR-10)
    role           TEXT NOT NULL
                   CHECK (role IN ('DRIVER', 'ADMIN', 'SUPPORT_AGENT')),
    failed_logins  INTEGER NOT NULL DEFAULT 0,      -- consecutive failures (SR-02)
    locked_until   TEXT,                            -- end of the 15-minute block (SR-02)
    last_login_at  TEXT,                            -- data map: detect 12 months of inactivity
    created_at     TEXT NOT NULL
);

-- Login sessions, kept on the server so logout and timeout really end them.
-- Only a SHA-256 hash of the cookie value is stored: a stolen copy of this
-- table cannot be used to log in.
CREATE TABLE IF NOT EXISTS login_sessions (
    token_hash    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

-- Vehicles: one driver can own several cars.
CREATE TABLE IF NOT EXISTS vehicles (
    id          TEXT PRIMARY KEY,                   -- vehicle ID (SR-07)
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plate_enc   TEXT NOT NULL,                      -- AES-256-GCM encrypted plate (PR-04)
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_owner ON vehicles(owner_id);

-- Parking spots. Spots hold no personal data.
CREATE TABLE IF NOT EXISTS spots (
    id      TEXT PRIMARY KEY,
    label   TEXT NOT NULL UNIQUE,
    status  TEXT NOT NULL CHECK (status IN ('FREE', 'OCCUPIED', 'DISABLED'))
);

-- Reservations: which vehicle holds which spot, and when.
CREATE TABLE IF NOT EXISTS reservations (
    id          TEXT PRIMARY KEY,
    driver_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vehicle_id  TEXT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    spot_id     TEXT NOT NULL REFERENCES spots(id),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    CHECK (end_time > start_time)
);
CREATE INDEX IF NOT EXISTS idx_reservations_spot_time ON reservations(spot_id, start_time);
CREATE INDEX IF NOT EXISTS idx_reservations_driver ON reservations(driver_id);

-- Parking history: linked by vehicle ID only, with no plate or email (PR-05).
-- Filled by the gate decision (FR-10, FR-11). spot_id records which spot the
-- car took, so the spot can be set to OCCUPIED on entry and back to FREE on
-- exit (FR-12). exit_time is NULL while the car is still inside.
CREATE TABLE IF NOT EXISTS parking_sessions (
    id          TEXT PRIMARY KEY,                   -- random UUID (SR-07)
    vehicle_id  TEXT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    spot_id     TEXT NOT NULL REFERENCES spots(id),
    entry_time  TEXT NOT NULL,
    exit_time   TEXT
);
CREATE INDEX IF NOT EXISTS idx_parking_sessions_vehicle ON parking_sessions(vehicle_id);

-- Disputes (FR-15 to FR-17): the reason comes from a fixed list, so there is
-- no free text that could hold extra personal data. While a driver has an OPEN
-- dispute, a support agent can see that driver's data (SR-06).
CREATE TABLE IF NOT EXISTS disputes (
    id                  TEXT PRIMARY KEY,           -- random UUID (SR-07)
    driver_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reservation_id      TEXT REFERENCES reservations(id) ON DELETE CASCADE,
    parking_session_id  TEXT REFERENCES parking_sessions(id) ON DELETE CASCADE,
    reason              TEXT NOT NULL CHECK (reason IN (
                            'GATE_DENIED_WITH_RESERVATION',
                            'WRONG_ENTRY_OR_EXIT_TIME',
                            'RESERVED_SPOT_TAKEN',
                            'RESERVATION_NOT_SHOWN')),
    status              TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    created_at          TEXT NOT NULL,
    closed_at           TEXT,
    -- A dispute is about exactly one reservation or one parking session.
    CHECK ((reservation_id IS NULL) <> (parking_session_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_disputes_driver_status ON disputes(driver_id, status);

-- Audit log: IDs only, never emails or plates (PR-06).
-- user_id has no foreign key on purpose: the data map keeps the ID in audit
-- entries after the account is deleted, until the entry expires.
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,            -- who acted; NULL when unknown (failed login)
    action      TEXT NOT NULL,
    target_id   TEXT,            -- what the action was about
    ip_address  TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

-- SR-23: audit entries cannot be changed by anyone, and cannot be deleted
-- before they are 180 days old (PR-10). Enforced inside the database, so even
-- a bug in the application code cannot rewrite the log.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit log entries cannot be changed');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_early_delete
BEFORE DELETE ON audit_log
WHEN OLD.created_at > strftime('%Y-%m-%d %H:%M:%S', 'now', '-180 days')
BEGIN
    SELECT RAISE(ABORT, 'audit log entries can only be deleted after 180 days');
END;

-- Schema version. run.py refuses to start with a database made by an older
-- version, instead of failing later on a missing column.
PRAGMA user_version = 2;
