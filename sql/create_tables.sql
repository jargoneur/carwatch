BEGIN TRANSACTION;

-- Users for login
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

-- Main entity: a scraped used-car listing
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- provenance
    source TEXT NOT NULL,
    external_id TEXT,
    url TEXT NOT NULL UNIQUE,

    -- normalized vehicle fields
    title TEXT,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    variant TEXT,
    year INTEGER,
    mileage_km INTEGER,
    price_eur INTEGER,
    fuel_type TEXT,
    transmission TEXT,
    color TEXT,
    accident INTEGER,
    condition TEXT,

    -- scoring (current)
    score REAL,
    score_version TEXT,
    score_computed_at TEXT,

    -- scoring diagnostics (useful for debugging/explanations)
    score_level TEXT,
    score_group_size INTEGER,
    score_price_percentile REAL,

    -- raw payload for future parsing/debugging
    raw_json TEXT,

    -- lifecycle
    first_seen_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    last_seen_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Time series: price/mileage changes over time
CREATE TABLE IF NOT EXISTS listing_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    price_eur INTEGER,
    mileage_km INTEGER,
    FOREIGN KEY (listing_id) REFERENCES listings (id) ON DELETE CASCADE
);

-- Time series: score changes over time
CREATE TABLE IF NOT EXISTS listing_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    score REAL NOT NULL,
    score_version TEXT,
    details_json TEXT,
    FOREIGN KEY (listing_id) REFERENCES listings (id) ON DELETE CASCADE
);

-- Aggregates per day for trend/statistics
CREATE TABLE IF NOT EXISTS model_year_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    n INTEGER NOT NULL,
    avg_price REAL,
    median_price REAL,
    avg_mileage REAL,
    median_mileage REAL,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE(snapshot_date, brand, model, year)
);

-- Helpful indexes for filtering/sorting
CREATE INDEX IF NOT EXISTS idx_listings_brand_model_year ON listings(brand, model, year);
CREATE INDEX IF NOT EXISTS idx_listings_score ON listings(score);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
CREATE INDEX IF NOT EXISTS idx_listings_mileage ON listings(mileage_km);
CREATE INDEX IF NOT EXISTS idx_listings_seen ON listings(last_seen_at);

COMMIT;
