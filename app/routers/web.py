# app/routers/web.py
import datetime
import json
import re
from typing import Optional
from fastapi import APIRouter, Request, Form, Response, status, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token, get_current_user_from_cookie
from app.templates_config import templates

router = APIRouter(tags=["Web Portal"])

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT content_json FROM site_content WHERE key = 'home'")
    row = cursor.fetchone()
    conn.close()

    content = json.loads(row["content_json"]) if row else {}
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"request": request, "user": user, "content": content}
    )

# ----------------- ASSET STORE (PUBLIC BROWSING ONLY) -----------------
@router.get("/assets", response_class=HTMLResponse)
def assets_store_catalog(request: Request,
                         type: Optional[str] = Query(None),
                         q: Optional[str] = Query(None)):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT id, slug, name, type, asset_status, latest_version, min_autocad,
           short_desc, thumb_32_url, thumb_64_url, is_pro, rating, rating_count,
           download_count, dev_name, commands_json, tags
    FROM assets
    """
    params = []
    conditions = []

    if type and type.strip() and type.strip().lower() != "all":
        conditions.append("type = ?")
        params.append(type.strip().lower())

    if q and q.strip():
        conditions.append("(name LIKE ? OR short_desc LIKE ? OR tags LIKE ?)")
        search_pattern = f"%{q.strip()}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY updated_at DESC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    assets = []
    for r in rows:
        item = dict(r)
        item["thumb_url"] = r["thumb_64_url"] or r["thumb_32_url"] or ""
        item["rating_val"] = float(r["rating"]) if (r["rating_count"] and r["rating_count"] > 0 and r["rating"] is not None) else 0.0

        try:
            raw_cmds = json.loads(r["commands_json"]) if r["commands_json"] else []
        except Exception:
            raw_cmds = []

        item["commands_count"] = len([c for c in raw_cmds if isinstance(c, dict) and c.get("command")])
        assets.append(item)

    return templates.TemplateResponse(
        request=request,
        name="assets_catalog.html",
        context={
            "request": request,
            "user": user,
            "assets": assets,
            "selected_type": type or "all",
            "search_query": q or ""
        }
    )

@router.get("/assets/{asset_id}", response_class=HTMLResponse)
def asset_store_detail(request: Request, asset_id: str):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset_row = cursor.fetchone()
    if not asset_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    asset = dict(asset_row)
    actual_id = asset["id"]

    cursor.execute("""
    SELECT author, text, rating, created_at
    FROM comments WHERE asset_id = ? ORDER BY id DESC LIMIT 20
    """, (actual_id,))
    comment_rows = cursor.fetchall()

    cursor.execute("SELECT version, release_notes, created_at FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (actual_id,))
    version_rows = cursor.fetchall()
    conn.close()

    try:
        raw_commands = json.loads(asset.get("commands_json") or "[]")
    except Exception:
        raw_commands = []

    try:
        raw_media = json.loads(asset.get("media_json") or "[]")
    except Exception:
        raw_media = []

    comments = []
    for c in comment_rows:
        item = dict(c)
        item["created_at_short"] = str(item.get("created_at") or "")[:10]
        comments.append(item)

    asset["thumb_url"] = asset.get("thumb_64_url") or asset.get("thumb_32_url") or ""
    asset["rating_val"] = float(asset["rating"]) if (asset.get("rating_count") and asset.get("rating_count") > 0 and asset.get("rating") is not None) else 0.0

    return templates.TemplateResponse(
        request=request,
        name="asset_detail.html",
        context={
            "request": request,
            "user": user,
            "asset": asset,
            "commands": raw_commands,
            "media_items": raw_media,
            "comments": comments,
            "versions": version_rows
        }
    )

# ----------------- DOWNLOADS -----------------
@router.get("/download", response_class=HTMLResponse)
def downloads_page(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM download_items WHERE is_active = 1 ORDER BY id DESC")
    downloads = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context={"request": request, "user": user, "downloads": downloads}
    )

@router.get("/download/{download_id}/file")
def download_file_action(download_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM download_items WHERE id = ? AND is_active = 1", (download_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Download item not found.")

    cursor.execute("UPDATE download_items SET download_count = download_count + 1 WHERE id = ?", (download_id,))
    conn.commit()
    conn.close()

    file_url = item["file_url"]
    return RedirectResponse(file_url, status_code=302)

# ----------------- BLOG -----------------
@router.get("/blog", response_class=HTMLResponse)
def blog_list_page(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE is_published = 1 ORDER BY id DESC")
    posts = cursor.fetchall()
    conn.close()

    formatted_posts = []
    for p in posts:
        item = dict(p)
        item["created_at_short"] = str(p["created_at"])[:10]
        formatted_posts.append(item)

    return templates.TemplateResponse(
        request=request,
        name="blog_list.html",
        context={"request": request, "user": user, "posts": formatted_posts}
    )

@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_detail_page(request: Request, slug: str):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE slug = ? AND is_published = 1", (slug.strip().lower(),))
    post_row = cursor.fetchone()
    conn.close()

    if not post_row:
        raise HTTPException(status_code=404, detail="Article not found.")

    post = dict(post_row)
    post["created_at_short"] = str(post["created_at"])[:10]
    try:
        post["gallery"] = json.loads(post["gallery_json"]) if post["gallery_json"] else []
    except Exception:
        post["gallery"] = []

    return templates.TemplateResponse(
        request=request,
        name="blog_detail.html",
        context={"request": request, "user": user, "post": post}
    )

# ----------------- ABOUT & CONTACT -----------------
@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT content_json FROM site_content WHERE key = 'about'")
    row = cursor.fetchone()
    conn.close()

    content = json.loads(row["content_json"]) if row else {}
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={"request": request, "user": user, "content": content}
    )

@router.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    user = get_current_user_from_cookie(request)
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={"request": request, "user": user, "success": None, "error": None}
    )

@router.post("/contact", response_class=HTMLResponse)
def contact_submit_action(request: Request,
                          name: str = Form(...),
                          email: str = Form(...),
                          phone: str = Form(""),
                          subject: str = Form("General Inquiry"),
                          message: str = Form(...)):
    user = get_current_user_from_cookie(request)
    now = datetime.datetime.utcnow().isoformat()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO contact_tickets (name, email, phone, subject, message, status, created_at)
    VALUES (?, ?, ?, ?, ?, 'open', ?)
    """, (name.strip(), email.strip().lower(), phone.strip(), subject.strip(), message.strip(), now))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "request": request,
            "user": user,
            "success": "Thank you! Your ticket has been registered. Our engineering support will contact you promptly.",
            "error": None
        }
    )

# ----------------- AUTHENTICATION -----------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "error": None}
    )

@router.post("/login", response_class=HTMLResponse)
def login_action(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Invalid email or password."}
        )

    if user["is_suspended"]:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Account suspended. Please contact support."}
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    cursor.execute("UPDATE users SET last_ip = ? WHERE id = ?", (client_ip, user["id"]))
    conn.commit()
    conn.close()

    token, _ = create_jwt_token(
        user["email"],
        f"{user['first_name']} {user['last_name']}",
        bool(user["is_admin"]),
        user["subscription_tier"]
    )
    target = "/admin" if user["is_admin"] else "/dashboard"
    redirect = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(key="access_token", value=token, httponly=True, max_age=3600 * 24 * 7)
    return redirect

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"request": request, "error": None}
    )

@router.post("/register", response_class=HTMLResponse)
def register_action(request: Request, first_name: str = Form(...), last_name: str = Form(...),
                    email: str = Form(...), phone: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"request": request, "error": "Email is already registered."}
        )

    hashed = hash_password(password)
    now = datetime.datetime.utcnow().isoformat()
    client_ip = request.client.host if request.client else "127.0.0.1"

    cursor.execute("""
    INSERT INTO users (email, phone, password_hash, first_name, last_name, last_ip, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email.lower().strip(), phone.strip(), hashed, first_name.strip(), last_name.strip(), client_ip, now))
    conn.commit()
    conn.close()

    return RedirectResponse("/login?registered=1", status_code=status.HTTP_302_FOUND)

@router.get("/logout")
def logout():
    redirect = RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie("access_token")
    return redirect

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user_payload["email"],))
    user = cursor.fetchone()
    conn.close()

    remaining_days = 0
    if user and user["subscription_expires_at"]:
        try:
            exp_date = datetime.datetime.fromisoformat(user["subscription_expires_at"])
            delta = exp_date - datetime.datetime.utcnow()
            remaining_days = max(0, delta.days)
        except Exception:
            remaining_days = 0

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"request": request, "user": user, "remaining_days": remaining_days}
    )

@router.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    user = get_current_user_from_cookie(request)
    if user and user.get("is_admin"):
        return RedirectResponse("/admin/plans", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY price_toman ASC")
    plan_rows = cursor.fetchall()
    conn.close()

    plans = []
    for p in plan_rows:
        item = dict(p)
        item["features"] = json.loads(p["features_json"]) if p["features_json"] else []
        plans.append(item)

    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context={"request": request, "user": user, "plans": plans}
    )

@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, plan_id: str = Query("monthly")):
    user = get_current_user_from_cookie(request)
    if user and user.get("is_admin"):
        return RedirectResponse("/admin", status_code=302)
    if not user:
        return RedirectResponse(f"/login?next=/checkout?plan_id={plan_id}", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscription_plans WHERE id = ? AND is_active = 1", (plan_id,))
    plan = cursor.fetchone()
    conn.close()

    if not plan:
        return RedirectResponse("/pricing", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={"request": request, "user": user, "plan": plan}
    )
