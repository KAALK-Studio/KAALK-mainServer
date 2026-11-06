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
        status TEXT NOT NULL,
        transaction_ref TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
    );
    """)

    # 7. Downloads table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS download_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        version TEXT NOT NULL,
        file_url TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        file_type TEXT DEFAULT 'exe',
        description TEXT,
        is_active INTEGER DEFAULT 1,
        download_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # 8. Blog posts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blog_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        summary TEXT,
        content TEXT NOT NULL,
        cover_image_url TEXT,
        gallery_json TEXT DEFAULT '[]',
        video_url TEXT,
        model_3d_url TEXT,
        author TEXT DEFAULT 'KAALK Architecture Studio',
        is_published INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 9. Contact tickets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contact_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        subject TEXT,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL
    );
    """)

    # 10. Site dynamic editable content
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS site_content (
        key TEXT PRIMARY KEY,
        content_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
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

    # Seed Subscription Plans if empty
    cursor.execute("SELECT COUNT(*) as count FROM subscription_plans")
    if cursor.fetchone()["count"] == 0:
        free_feats = json.dumps(["Palette Asset Discovery", "Free Community Tools", "Command Alias Registration"])
        monthly_feats = json.dumps(["Full Access to Pro Suites & Tools", "Direct Command Integration", "Automatic Background Updates", "30 Days Full Access"])
        annual_feats = json.dumps(["Full Access to Pro Suites & Tools", "Direct Command Integration", "Priority Support Channel", "Pay for 10 Months, Get 12 Months", "Automatic Annual Renewal"])
        promo_feats = json.dumps(["Festival Special Access", "Full Pro Access During Event", "Bonus Pattern Bundles"])
        enterprise_feats = json.dumps(["Centralized Multi-Seat Licensing", "Custom In-House Tool Deployment", "Dedicated Private Cloud Asset Host", "24/7 SLA Technical Consultation"])

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

    # Seed Default Home and About Content if missing
    cursor.execute("SELECT key FROM site_content WHERE key = 'home'")
    if not cursor.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        home_seed = {
            "hero_title": "Enterprise Asset & Tool Management Inside AutoCAD",
            "hero_subtitle": "Discover, install, update, and hot-load professional architectural tools, dynamic blocks, and AutoLISP routines without leaving your drawing canvas.",
            "cta_download_text": "Download Plugin Installer",
            "cta_pricing_text": "Explore Pro Plans",
            "feature1_title": "Zero AutoCAD Restarts",
            "feature1_desc": "Integrated Command Proxy architecture loads and hot-swaps tools and commands in real time.",
            "feature2_title": "Two-Tier Catalog Manifests",
            "feature2_desc": "Ultra-fast palette browsing with on-demand retrieval of commands, documentation, and tutorial media.",
            "feature3_title": "AutoCAD PGP Synchronization",
            "feature3_desc": "Native alias injection into acad.pgp ensures native shortcut typing and command autocomplete."
        }
        cursor.execute("INSERT INTO site_content (key, content_json, updated_at) VALUES ('home', ?, ?)", (json.dumps(home_seed), now))

    cursor.execute("SELECT key FROM site_content WHERE key = 'about'")
    if not cursor.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        about_seed = {
            "title": "About KAALK Studio",
            "mission": "Bridging modern asynchronous cloud platforms with professional desktop CAD environments.",
            "story": "KAALK Asset Manager was founded by architects and CAD engineers to eradicate manual AutoLISP script deployment, broken paths, and version collisions across drafting teams.",
            "team": [
                {"name": "Masoud Nasiri", "role": "Lead Architect & Software Engineer", "bio": "Specialized in AutoCAD .NET API development, computational design, and cloud architecture."},
                {"name": "KAALK Core Team", "role": "CAD Tool & Content Development", "bio": "Creating high-performance architectural drafting utilities and dynamic parametric packages."}
            ]
        }
        cursor.execute("INSERT INTO site_content (key, content_json, updated_at) VALUES ('about', ?, ?)", (json.dumps(about_seed), now))

    conn.commit()
    conn.close()
