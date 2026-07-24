-- Core RFQ Intelligence Platform schema
-- Works as-is on SQLite.

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT,
    region          TEXT,
    gst_no          TEXT,
    pan_no          TEXT,
    msme_status     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rfqs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_number      TEXT NOT NULL,
    part_no         TEXT,
    part_description TEXT,
    quantity        REAL,
    uom             TEXT,
    due_date        TEXT,
    status          TEXT DEFAULT 'open',
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(rfq_number)
);

CREATE TABLE IF NOT EXISTS quotations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id          INTEGER NOT NULL REFERENCES rfqs(id),
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id),
    price           REAL,
    currency        TEXT DEFAULT 'INR',
    moq             REAL,
    lead_time_days  INTEGER,
    payment_terms   TEXT,
    validity        TEXT,
    raw_extraction_json TEXT,
    confidence_score REAL,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT NOT NULL UNIQUE,
    original_filename TEXT,
    mime_type       TEXT,
    sender_email    TEXT,
    rfq_id          INTEGER REFERENCES rfqs(id),
    quotation_id    INTEGER REFERENCES quotations(id),
    file_path       TEXT,
    extraction_status TEXT DEFAULT 'pending',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_quotations_rfq ON quotations(rfq_id);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_rfqs_status ON rfqs(status);
