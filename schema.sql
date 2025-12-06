DROP TABLE IF EXISTS records;

CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date DATE NOT NULL DEFAULT CURRENT_DATE,
    billing_month TEXT NOT NULL, -- Format: YYYY-MM
    meter_reading REAL NOT NULL,
    total_bill REAL NOT NULL,
    
    -- Calculated Fields
    usage REAL, -- Usage since last reading
    user_cost REAL,
    neighbor_cost REAL,
    calculation_note TEXT, -- Stores the formula/breakdown
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
