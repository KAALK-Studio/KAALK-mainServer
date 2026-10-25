from fastapi import Request
from fastapi.templating import Jinja2Templates
from app.services.i18n import get_locale_data, translate, SUPPORTED_LANGUAGES

def locale_context_processor(request: Request):
    lang_code = request.cookies.get("site_lang", "en")
    locale = get_locale_data(lang_code)
    return {
        "request": request,
        "locale": locale,
        "available_languages": [
            {"code": code, "name": meta.get("name", code)}
            for code, meta in SUPPORTED_LANGUAGES.items()
        ],
        "t": lambda key, default=None: translate(lang_code, key, default)
    }

templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[locale_context_processor]
)

# Safe fallback globals so templates never fail with undefined errors
default_locale = get_locale_data("en")
templates.env.globals["t"] = lambda key, default=None: translate("en", key, default)
templates.env.globals["locale"] = default_locale
templates.env.globals["available_languages"] = [
    {"code": code, "name": meta.get("name", code)}
    for code, meta in SUPPORTED_LANGUAGES.items()
]