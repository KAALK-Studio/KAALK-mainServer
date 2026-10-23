from fastapi import Request
from fastapi.responses import RedirectResponse
from app.services.i18n import get_locale_data, translate, SUPPORTED_LANGUAGES

# Inject locale helper into templates context
def template_locale_context(request: Request):
    lang_code = request.cookies.get("site_lang", "en")
    locale_meta = get_locale_data(lang_code)
    return {
        "locale": locale_meta,
        "available_languages": [
            {"code": code, "name": meta.get("name", code)} 
            for code, meta in SUPPORTED_LANGUAGES.items()
        ],
        "t": lambda key, default=None: translate(lang_code, key, default)
    }

# Endpoint to switch language and save preference in cookie
@app.get("/set-language/{lang_code}")
def set_language(request: Request, lang_code: str):
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=302)
    response.set_cookie(key="site_lang", value=lang_code.lower().strip(), max_age=3600 * 24 * 365)
    return response