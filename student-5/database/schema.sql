CREATE TABLE IF NOT EXISTS customer_preferences (
    preference_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL UNIQUE,
    product_category_interests TEXT NOT NULL DEFAULT '',
    preferred_brands TEXT NOT NULL DEFAULT '',
    price_range_min REAL DEFAULT 0,
    price_range_max REAL DEFAULT 500,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS browsing_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_spent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    recommended_product_id INTEGER NOT NULL,
    recommendation_score REAL NOT NULL DEFAULT 0,
    explanation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendation_feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL,
    customer_feedback_rating INTEGER CHECK (customer_feedback_rating >= 1 AND customer_feedback_rating <= 5),
    was_purchased BOOLEAN DEFAULT 0,
    helpful BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recommendation_id) REFERENCES recommendations(recommendation_id)
);

CREATE INDEX IF NOT EXISTS idx_browsing_customer ON browsing_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_customer ON recommendations(customer_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_product ON recommendations(recommended_product_id);
