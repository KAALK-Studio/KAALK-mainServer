import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import STORAGE_DIR
from app.database import init_db
from app.routers import auth_api, store_api, web, admin

# Initialize database tables on boot
init_db()

# Initialize FastAPI application instance
app = FastAPI(title="KAALK Platform Service", version="1.0.0")

# Mount storage directory for direct binary package downloads
app.mount("/static", StaticFiles(directory=STORAGE_DIR), name="static")

# Route for switching portal display language
@app.get("/set-language/{lang_code}")
def set_language(request: Request, lang_code: str):
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=302)
    response.set_cookie(
        key="site_lang",
        value=lang_code.lower().strip(),
        max_age=3600 * 24 * 365
    )
    return response

# Include JSON API routers for AutoCAD plugin
app.include_router(auth_api.router)
app.include_router(store_api.router)

# Include Web portal routers
app.include_router(web.router)
app.include_router(admin.router)

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=5000, reload=True)