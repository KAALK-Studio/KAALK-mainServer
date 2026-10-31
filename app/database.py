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

    # 9. Dynamic Site Pages CMS table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS site_pages (
        page_key TEXT PRIMARY KEY,
        title TEXT NOT NULL,
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

    # Seed Subscription Plans if missing
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

    # Seed Dynamic Site Pages CMS Defaults
    now = datetime.datetime.utcnow().isoformat()
    default_pages = [
        ("home", "Home Page", {
            "hero_badge": "AutoCAD 2018 - 2026+ Certified Runtime",
            "hero_title": "Supercharge Your Drafting directly inside AutoCAD",
            "hero_subtitle": "Discover, hot-load, and run precision architectural tools, construction line suites, dynamic blocks, and verified LISP routines without leaving your drawing viewport.",
            "cta_download_text": "Download AutoCAD Plugin (v0.5.2)",
            "cta_store_text": "Explore Asset Showcase",
            "pillar1_title": "Hot-Plug Command Proxy",
            "pillar1_desc": "Switch between tool versions on the fly. Commands load into memory dynamically without ever requiring an AutoCAD restart.",
            "pillar2_title": "Zero Registry Bloat",
            "pillar2_desc": "Tools follow the clean KAALK execution proxy. Uninstalled tools leave zero stale command residues inside your CAD workspace.",
            "pillar3_title": "Encrypted Cloud Sync",
            "pillar3_desc": "Windows DPAPI encrypted credentials guarantee instant offline validation and seamless pro tool unlock across your firm."
        }),
        ("download", "Download Page", {
            "badge_text": "Official Verified Client",
            "version": "0.5.2",
            "headline": "Download KAALK for Autodesk AutoCAD",
            "subheadline": "Direct client installer package compiled natively for Windows 64-bit systems.",
            "package_name": "KaalkAssetManager.zip",
            "package_description": "Includes compiled KaalkAssetManager.dll, architecture manifests, and runner scripts.",
            "sha256": "8f3b2a5c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a",
            "step1_title": "Download & Extract",
            "step1_desc": "Download the ZIP archive and extract KaalkAssetManager.dll to a permanent directory on your workstation (e.g. C:\\CAD_Tools\\KAALK\\).",
            "step2_title": "Launch AutoCAD",
            "step2_desc": "Open your drawing project in Autodesk AutoCAD 2018 or newer (Architecture, Civil 3D, and MEP supported).",
            "step3_title": "Netload Assembly",
            "step3_desc": "Type NETLOAD in the AutoCAD command line and select KaalkAssetManager.dll.",
            "step4_title": "Launch Palette",
            "step4_desc": "Type KAALK to open your in-app marketplace palette and begin discovering CAD tools."
        }),
        ("store", "Store Showcase", {
            "headline": "CAD Asset & Tool Showcase",
            "subheadline": "Browse the catalog of verified tools, dynamic blocks, patterns, and LISP routines.",
            "banner_title": "Direct In-CAD Execution Only",
            "banner_text": "To maintain cryptographic integrity and dynamic hot-plugging, assets are discovered and installed exclusively inside AutoCAD via the KAALK palette."
        }),
        ("pricing", "Pricing & Plans", {
            "headline": "Professional Subscription Plans",
            "subheadline": "Flexible access to specialized AutoCAD plugins, scripts, and updates directly inside your palette.",
            "guarantee_text": "Instant activation upon payment completion. Cancel or upgrade anytime."
        }),
        ("about", "About Us", {
            "headline": "Architectural Engineering Meets Cloud Runtimes.",
            "subheadline": "KAALK Asset Manager was founded by architects and CAD engineers who spent decades battling broken network shares, unversioned LISP scripts, and system crashes caused by static command collisions.",
            "mission_title": "Our Core Engineering Mission",
            "mission_desc": "Our mission is to establish a verified, cloud-synced runtime for AutoCAD. We believe CAD operators should discover, test, and run professional utilities without leaving their viewport, without wrestling with complex installation paths, and with guaranteed rollback safety.",
            "pillar1_title": "Strict 5-Layer Architectural Integrity",
            "pillar1_desc": "Our AutoCAD client assembly strictly isolates Security (DPAPI), Core API, Presenters, WPF UI, and Host wrappers. It runs zero external NuGet dependencies for maximum stability in enterprise environments.",
            "pillar2_title": "Pure Command Proxy & Hot-Plug",
            "pillar2_desc": "By moving away from static hard-coded AutoCAD attributes, tools hot-swap instantly across versions without AutoCAD reboots and cleanly detach upon uninstallation."
        }),
        ("contact", "Contact & Support", {
            "headline": "Get in Touch with KAALK Engineering",
            "subheadline": "Have an inquiry regarding multi-seat enterprise deployment, private tool publishing, or client support?",
            "email": "support@kaalk.ir",
            "phone": "+98 (21) 8800-0000",
            "response_time": "Under 24 Business Hours",
            "address": "KAALK Innovation Studio, Tehran, Iran"
        })
    ]

    for key, title, content in default_pages:
        cursor.execute("SELECT page_key FROM site_pages WHERE page_key = ?", (key,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO site_pages (page_key, title, content_json, updated_at)
            VALUES (?, ?, ?, ?)
            """, (key, title, json.dumps(content), now))

    conn.commit()
    conn.close()
    
