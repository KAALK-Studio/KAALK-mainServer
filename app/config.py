# app/config.py
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
PACKAGES_DIR = os.path.join(STORAGE_DIR, "packages")
MEDIA_DIR = os.path.join(STORAGE_DIR, "media")
DOWNLOADS_DIR = os.path.join(STORAGE_DIR, "downloads")
BLOG_DIR = os.path.join(STORAGE_DIR, "blog")
DB_PATH = os.path.join(BASE_DIR, "kaalk.db")

APP_VERSION = "0.1.0"
SECRET_KEY = os.environ.get("KAALK_SECRET_KEY", "KAALK_SECRET_KEY_PRODUCTION_DEFAULT_REPLACE")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Maildir and SMTP Configuration
DEFAULT_MAILDIR = "/home/info/Maildir"
FALLBACK_MAILDIR = os.path.join(STORAGE_DIR, "maildir")
MAILDIR_PATH = os.environ.get("KAALK_MAILDIR_PATH", DEFAULT_MAILDIR if os.path.exists("/home/info") else FALLBACK_MAILDIR)

SMTP_HOST = os.environ.get("KAALK_SMTP_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("KAALK_SMTP_PORT", 25))
SMTP_FROM = os.environ.get("KAALK_SMTP_FROM", "info@kaalk.ir")

os.makedirs(PACKAGES_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)