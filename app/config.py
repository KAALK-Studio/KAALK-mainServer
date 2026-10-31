# app/config.py
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
PACKAGES_DIR = os.path.join(STORAGE_DIR, "packages")
MEDIA_DIR = os.path.join(STORAGE_DIR, "media")
DOWNLOADS_DIR = os.path.join(STORAGE_DIR, "downloads")
DB_PATH = os.path.join(BASE_DIR, "kaalk.db")

SECRET_KEY = "KAALK_SECRET_KEY_PRODUCTION_REPLACE"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ZarinPal payment gateway configuration
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "00000000-0000-0000-0000-000000000000")
ZARINPAL_SANDBOX = os.getenv("ZARINPAL_SANDBOX", "true").lower() == "true"

# Ensure storage directories exist
os.makedirs(PACKAGES_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
