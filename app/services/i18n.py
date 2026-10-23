import os
import json
from typing import Dict, Any

LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locales")
SUPPORTED_LANGUAGES: Dict[str, Dict[str, Any]] = {}

def load_locales():
    if not os.path.exists(LOCALES_DIR):
        os.makedirs(LOCALES_DIR, exist_ok=True)
        return

    for filename in os.listdir(LOCALES_DIR):
        if filename.endswith(".json"):
            lang_code = filename[:-5].lower()
            file_path = os.path.join(LOCALES_DIR, filename)
            try:
                with open(file_path, "r", encoding="ascii", errors="ignore") as f:
                    data = json.load(f)
                    SUPPORTED_LANGUAGES[lang_code] = data
            except Exception:
                pass

# Initial load on module import
load_locales()

def get_locale_data(lang_code: str) -> Dict[str, Any]:
    lang_code = (lang_code or "en").lower().strip()
    return SUPPORTED_LANGUAGES.get(lang_code, SUPPORTED_LANGUAGES.get("en", {
        "code": "en",
        "name": "English",
        "dir": "ltr",
        "font_family": "sans-serif",
        "font_url": "",
        "translations": {}
    }))

def translate(lang_code: str, key: str, default: str = None) -> str:
    locale = get_locale_data(lang_code)
    translations = locale.get("translations", {})
    return translations.get(key, default or key)