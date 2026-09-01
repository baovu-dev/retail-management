CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 and rating <= 5),
    comment TEXT,
    sentiment_score FLOAT,
    is_flagged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    --FOREIGN KEY (product_id) REFERENCES products(product_id),
    --FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS review_summaries (
    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL UNIQUE,
    generated_summary TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    --FOREIGN KEY (product_id) REFERENCES products(product_id)
);
