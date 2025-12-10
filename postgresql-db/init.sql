CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    company VARCHAR(255),
    email VARCHAR(255),
    source VARCHAR(255),
    submitted_at TIMESTAMP DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS unique_email_index ON users (email);
