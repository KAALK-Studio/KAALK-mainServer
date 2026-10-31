# app/database.py
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

    # 1. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        is_suspended INTEGER DEFAULT 0,
        subscription_tier TEXT DEFAULT 'free',
        subscription_expires_at TEXT,
        last_ip TEXT DEFAULT '127.0.0.1',
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
        asset_status TEXT DEFAULT 'stable',
        min_autocad INTEGER DEFAULT 2018,
        short_desc TEXT,
        full_desc TEXT,
        thumb_32_url TEXT,
        thumb_64_url TEXT,
        is_pro INTEGER DEFAULT 0,
        rating REAL DEFAULT 5.0,
        rating_count INTEGER DEFAULT 0,
        download_count INTEGER DEFAULT 0,
        monthly_downloads INTEGER DEFAULT 0,
        dev_id TEXT,
        dev_name TEXT,
        dev_website TEXT,
        commands_json TEXT DEFAULT '[]',
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
        commands_json TEXT DEFAULT '[]',
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
        user_id INTEGER,
        author TEXT NOT NULL,
        text TEXT NOT NULL,
        rating INTEGER DEFAULT 5,
        created_at TEXT NOT NULL,
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # 5. Subscription Plans table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscription_plans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price_toman INTEGER NOT NULL,
        duration_days INTEGER NOT NULL,
        billing_cycle TEXT NOT NULL,
        discount_percent INTEGER DEFAULT 0,
        discount_badge TEXT,
        discount_expires_at TEXT,
        description TEXT,
        features_json TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 6. Payments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan_id TEXT NOT NULL,
        amount_toman INTEGER NOT NULL,
        gateway TEXT DEFAULT 'zarinpal',
        authority TEXT,
        status TEXT NOT NULL,
        transaction_ref TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
    );
    """)

    # 7. Blog Articles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        summary TEXT,
        content TEXT NOT NULL,
        banner_url TEXT,
        category TEXT DEFAULT 'Architecture',
        tags TEXT,
        author_name TEXT DEFAULT 'KAALK Studio',
        is_published INTEGER DEFAULT 1,
        view_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 8. Contact Inquiries table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contact_inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        is_resolved INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Seed Admin User if missing
    cursor.execute("SELECT id FROM users WHERE email = 'admin@kaalk.ir'")
    if not cursor.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute("""
        INSERT INTO users (email, phone, password_hash, first_name, last_name, is_admin, is_suspended, subscription_tier, last_ip, created_at)
        VALUES ('admin@kaalk.ir', '+989120000000', ?, 'Admin', 'KAALK', 1, 0, 'premium', '5.200.200.1', ?)
        """, (hash_password("Admin@12345"), now))

    # Seed Subscription Plans
    cursor.execute("SELECT COUNT(*) as count FROM subscription_plans")
    if cursor.fetchone()["count"] == 0:
        free_feats = json.dumps([
            "Palette Asset Discovery",
            "Free Community Tools",
            "Command Alias Registration"
        ])
        monthly_feats = json.dumps([
            "Full Access to Pro Suites & Tools",
            "Direct Command Integration",
            "Automatic Background Updates",
            "30 Days Full Access"
        ])
        annual_feats = json.dumps([
            "Full Access to Pro Suites & Tools",
            "Direct Command Integration",
            "Priority Support Channel",
            "Pay for 10 Months, Get 12 Months",
            "Automatic Annual Renewal"
        ])
        promo_feats = json.dumps([
            "Festival Special Access",
            "Full Pro Access During Event",
            "Bonus Pattern Bundles"
        ])
        enterprise_feats = json.dumps([
            "Centralized Multi-Seat Licensing",
            "Custom In-House Tool Deployment",
            "Dedicated Private Cloud Asset Host",
            "24/7 SLA Technical Consultation"
        ])

        monthly_price = 350000
        annual_price = monthly_price * 10

        cursor.execute("""
        INSERT INTO subscription_plans (id, name, price_toman, duration_days, billing_cycle, discount_percent, discount_badge, discount_expires_at, description, features_json, is_active)
        VALUES
        ('free', 'Free Tier', 0, 0, 'Permanent', 0, '', NULL, 'Basic drafting utilities and discovery.', ?, 1),
        ('monthly', 'Monthly Pro', ?, 30, 'Monthly', 0, '', NULL, 'Flexible professional monthly subscription.', ?, 1),
        ('annual', 'Annual Pro', ?, 365, 'Yearly', 17, '2 Months Free', NULL, 'Annual pass with 2 months free.', ?, 1),
        ('promo', 'Special Promo', 245000, 30, 'One-time', 30, '30% Discount', NULL, 'Limited-time special occasion promotional access.', ?, 1),
        ('enterprise', 'Enterprise Organization', 15000000, 365, 'Yearly', 0, 'Custom Fleet', NULL, 'Dedicated multi-seat deployment for engineering firms.', ?, 0)
        """, (free_feats, monthly_price, monthly_feats, annual_price, annual_feats, promo_feats, enterprise_feats))

    # Seed Blog Articles if empty
    cursor.execute("SELECT COUNT(*) as count FROM articles")
    if cursor.fetchone()["count"] == 0:
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute("""
        INSERT INTO articles (slug, title, summary, content, category, tags, author_name, is_published, view_count, created_at, updated_at)
        VALUES
        ('mastering-infinite-xlines-autocad',
         'Mastering Precision Viewport XLines in AutoCAD',
         'Discover how non-intrusive construction lines accelerate complex geometric alignments in architectural layouts.',
         '### Overview\n\nPrecision drafting relies on clean reference lines. Traditional methods clutter drawing layers with residual construction lines.\n\nWith the **KAALK XLine Suite**, construction lines adapt directly to the user coordinate system (UCS).\n\n```text\nCommand: XLV (Vertical XLine)\nCommand: XLH (Horizontal XLine)\nCommand: XLS (Bisecting XLine)\n```\n\n- Pure dynamic injection ensures zero registry bloat.\n- Automatically aligns with current viewport transformations.\n- Safe execution without document locks.\n\nTry it now inside AutoCAD using the in-app palette.',
         'Tutorials',
         'autocad, drafting, xlines, productivity',
         'KAALK Studio', 1, 142, ?, ?),
        ('kaalk-modular-cad-architecture',
         'Building Cloud-Native Asset Workflows for Engineering Teams',
         'How decoupled command dispatching and cloud packages eliminate outdated LISP and ARX deployment headaches.',
         '### The Legacy CAD Deployment Problem\n\nFor decades, engineering firms maintained shared network drives with hundreds of unversioned `.lsp` and `.arx` scripts. Whenever AutoCAD was updated, legacy routines failed without actionable traces.\n\n### The KAALK Solution\n\n1. **Two-Tier Dynamic Catalogs**: Fast catalog indexing in milliseconds.\n2. **Pure Command Proxies**: Hot-pluggable commands registered without static command collision.\n3. **DPAPI Encrypted Client Sessions**: Seamless cloud entitlement verification.\n\nExperience the next generation of drafting tools directly inside AutoCAD 2018+.',
         'Architecture',
         'engineering, bim, cloud, autocad',
         'KAALK Architecture Team', 1, 98, ?, ?)
        """, (now, now, now, now))

    conn.commit()
    conn.close()
