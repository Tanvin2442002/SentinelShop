CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'customer'
                  CHECK (role IN ('customer', 'admin')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    id         SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    status     TEXT NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- DEMO users for the lab only (fake passwords, bcrypt-hashed).
INSERT INTO users (username, password_hash, role) VALUES
    ('alice', crypt('alice-demo-pw', gen_salt('bf')), 'customer'),
    ('bob',   crypt('bob-demo-pw',   gen_salt('bf')), 'customer'),
    ('admin', crypt('admin-demo-pw', gen_salt('bf')), 'admin')
ON CONFLICT (username) DO NOTHING;

-- Seed catalog, only if the table is empty.
INSERT INTO products (name, price, stock)
SELECT * FROM (VALUES
    ('Wireless Mouse',           19.99, 100),
    ('Mechanical Keyboard',      79.90,  50),
    ('USB-C Hub',                34.50,  80),
    ('27in Monitor',            229.00,  20),
    ('Webcam HD',                49.99,  60),
    ('Laptop Stand',             29.95,  75),
    ('Noise-Cancelling Headset',129.00,  40),
    ('External SSD 1TB',         99.00,  35),
    ('Desk Lamp',                24.50,  90),
    ('Ergonomic Chair',         289.00,  15),
    ('HDMI Cable',                9.99, 200),
    ('Power Bank 20000mAh',      39.90,  70)
) AS v(name, price, stock)
WHERE NOT EXISTS (SELECT 1 FROM products);
