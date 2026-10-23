import sqlite3
import datetime
import json
from app.config import DB_PATH
from app.security import hash_password

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Users table with suspension flag
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        is_suspended INTEGER DEFAULT 0,
        subscription_tier TEXT DEFAULT 'free',
        subscription_expires_at TEXT,
        reset_token TEXT,
        reset_token_expires TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Assets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        min_autocad INTEGER DEFAULT 2018,
        short_desc TEXT,
        full_desc TEXT,
        thumb_32_url TEXT,
        thumb_64_url TEXT,
        is_pro INTEGER DEFAULT 0,
        rating REAL DEFAULT 5.0,
        rating_count INTEGER DEFAULT 0,
        download_count INTEGER DEFAULT 0,
        dev_id TEXT,
        dev_name TEXT,
        dev_website TEXT,
        default_command TEXT,
        default_alias TEXT,
        tags TEXT,
        media_json TEXT,
        latest_version TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 3. Asset Versions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asset_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id TEXT NOT NULL,
        version TEXT NOT NULL,
        release_notes TEXT,
        download_url TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        UNIQUE(asset_id, version)
    );
    """)

    # 4. Comments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id TEXT NOT NULL,
        author TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (asset_id) REFERENCES assets(id)
    );
    """)

    # 5. Subscription Plans table (with discount & special offer support)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscription_plans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price_toman INTEGER NOT NULL,
        duration_days INTEGER NOT NULL,
        billing_cycle TEXT NOT NULL,
        discount_badge TEXT,
        description TEXT,
        features_json TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 6. Orders and Payment transactions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan_id TEXT NOT NULL,
        amount_toman INTEGER NOT NULL,
        status TEXT NOT NULL,
        transaction_ref TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
    );
    """)

    # Seed Admin User if missing
    cursor.execute("SELECT id FROM users WHERE email = 'admin@kaalk.ir'")
    if not cursor.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute("""
        INSERT INTO users (email, password_hash, first_name, last_name, is_admin, is_suspended, subscription_tier, created_at)
        VALUES ('admin@kaalk.ir', ?, 'Admin', 'KAALK', 1, 0, 'premium', ?)
        """, (hash_password("Admin@12345"), now))

    # Seed Plans (Free, Monthly 299k Toman, Annual 2990k Toman with 2 months free, Special Offer)
    cursor.execute("SELECT COUNT(*) as count FROM subscription_plans")
    if cursor.fetchone()["count"] == 0:
        free_feats = json.dumps([
            "Palette Asset Discovery",
            "Free Community LISP Tools",
            "Command Alias Registration"
        ])
        monthly_feats = json.dumps([
            "Full Access to Pro LISP & Tools",
            "Direct Command Integration",
            "Background Updates Support",
            "Monthly Renewable Access"
        ])
        annual_feats = json.dumps([
            "Full Access to Pro LISP & Tools",
            "Direct Command Integration",
            "Priority Support Channel",
            "12 Months Access for Price of 10",
            "2 Months Free Included"
        ])
        special_feats = json.dumps([
            "Limited Holiday Season Pass",
            "Full Pro Access for 90 Days",
            "Exclusive Architectural Hatch Bundles"
        ])

        cursor.execute("""
        INSERT INTO subscription_plans (id, name, price_toman, duration_days, billing_cycle, discount_badge, description, features_json, is_active)
        VALUES
        ('free', 'Free Tier', 0, 0, 'Free Forever', '', 'Standard basic access for drafting.', ?, 1),
        ('monthly', 'Monthly Pro', 299000, 30, '30 Days', '', 'Standard professional subscription.', ?, 1),
        ('annual', 'Annual Pro', 2990000, 365, '365 Days', '2 Months Free (Save 17%)', 'Best value annual commitment.', ?, 1),
        ('special', 'Seasonal Festival Pass', 699000, 90, '90 Days', 'Special 35% Discount', 'Occasional promotional package.', ?, 0)
        """, (free_feats, monthly_feats, annual_feats, special_feats))

    conn.commit()
    conn.close()