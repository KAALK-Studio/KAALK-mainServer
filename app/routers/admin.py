# app/routers/admin.py
import os
import json
import datetime
from typing import List, Optional
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from app.database import get_db
from app.security import hash_password, get_current_user_from_cookie
from app.services.package_service import PackageService
from app.templates_config import templates

router = APIRouter(prefix="/admin", tags=["Admin Panel"])

def require_admin(request: Request):
    user = get_current_user_from_cookie(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user

@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as c FROM users")
    total_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE subscription_tier = 'premium'")
    pro_users = cursor.fetchone()["c"]

    now = datetime.datetime.utcnow()
    d1 = (now - datetime.timedelta(days=1)).isoformat()
    d7 = (now - datetime.timedelta(days=7)).isoformat()
    d30 = (now - datetime.timedelta(days=30)).isoformat()

    def get_growth(since_date):
        cursor.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN subscription_tier = 'premium' THEN 1 ELSE 0 END) as pro 
        FROM users WHERE created_at >= ?
        """, (since_date,))
        row = cursor.fetchone()
        tot = row["total"] or 0
        pro = row["pro"] or 0
        return tot - pro, pro, tot

    day_free, day_pro, day_total = get_growth(d1)
    week_free, week_pro, week_total = get_growth(d7)
    month_free, month_pro, month_total = get_growth(d30)

    month_start = datetime.datetime(now.year, now.month, 1).isoformat()
    cursor.execute("""
    SELECT SUM(amount_toman) as rev 
    FROM payments 
    WHERE status = 'completed' AND completed_at >= ?
    """, (month_start,))
    monthly_revenue = cursor.fetchone()["rev"] or 0

    cursor.execute("SELECT COUNT(*) as c, SUM(download_count) as total_dl, SUM(monthly_downloads) as m_dl FROM assets")
    asset_stat = cursor.fetchone()
    total_assets = asset_stat["c"] or 0
    monthly_downloads = asset_stat["m_dl"] or 0

    cursor.execute("SELECT name, download_count, rating, rating_count FROM assets ORDER BY download_count DESC LIMIT 1")
    top_asset = cursor.fetchone()

    cursor.execute("SELECT name, rating, rating_count FROM assets WHERE rating_count > 0 ORDER BY rating ASC LIMIT 1")
    low_asset = cursor.fetchone()

    cursor.execute("SELECT DISTINCT last_ip FROM users LIMIT 30")
    ip_rows = cursor.fetchall()
    geo_nodes = []
    for r in ip_rows:
        ip_hash = hash(r["last_ip"])
        x = 20 + abs(ip_hash % 60)
        y = 20 + abs((ip_hash // 100) % 55)
        geo_nodes.append({"ip": r["last_ip"], "x": x, "y": y})

    conn.close()

    growth = {
        "day_free": day_free, "day_pro": day_pro, "day_total": day_total,
        "week_free": week_free, "week_pro": week_pro, "week_total": week_total,
        "month_free": month_free, "month_pro": month_pro, "month_total": month_total
    }

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "request": request,
            "user": user,
            "total_users": total_users,
            "pro_users": pro_users,
            "total_assets": total_assets,
            "monthly_revenue": monthly_revenue,
            "monthly_downloads": monthly_downloads,
            "growth": growth,
            "top_asset": top_asset,
            "low_asset": low_asset,
            "geo_nodes": geo_nodes
        }
    )

# --- Blog Articles Management ---

@router.get("/blog", response_class=HTMLResponse)
def admin_blog_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/blog.html",
        context={"request": request, "user": user, "articles": articles}
    )

@router.get("/blog/new", response_class=HTMLResponse)
def admin_blog_create_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/blog_edit.html",
        context={"request": request, "user": user, "article": None, "error": None}
    )

@router.post("/blog/new", response_class=HTMLResponse)
def admin_blog_create_action(request: Request,
                             title: str = Form(...),
                             slug: str = Form(...),
                             category: str = Form("Architecture"),
                             summary: str = Form(""),
                             content: str = Form(...),
                             tags: str = Form(""),
                             author_name: str = Form("KAALK Studio"),
                             is_published: bool = Form(False)):
    user = require_admin(request)
    clean_slug = slug.strip().lower()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE slug = ?", (clean_slug,))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="admin/blog_edit.html",
            context={"request": request, "user": user, "article": None, "error": "Slug already exists."}
        )

    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO articles (slug, title, summary, content, category, tags, author_name, is_published, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (clean_slug, title.strip(), summary.strip(), content.strip(), category.strip(),
          tags.strip(), author_name.strip(), 1 if is_published else 0, now, now))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/blog", status_code=302)

@router.get("/blog/{article_id}/edit", response_class=HTMLResponse)
def admin_blog_edit_page(request: Request, article_id: int):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cursor.fetchone()
    conn.close()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")

    return templates.TemplateResponse(
        request=request,
        name="admin/blog_edit.html",
        context={"request": request, "user": user, "article": article, "error": None}
    )

@router.post("/blog/{article_id}/edit", response_class=HTMLResponse)
def admin_blog_edit_action(request: Request,
                           article_id: int,
                           title: str = Form(...),
                           slug: str = Form(...),
                           category: str = Form("Architecture"),
                           summary: str = Form(""),
                           content: str = Form(...),
                           tags: str = Form(""),
                           author_name: str = Form("KAALK Studio"),
                           is_published: bool = Form(False)):
    user = require_admin(request)
    clean_slug = slug.strip().lower()

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE articles SET
        slug = ?, title = ?, summary = ?, content = ?, category = ?,
        tags = ?, author_name = ?, is_published = ?, updated_at = ?
    WHERE id = ?
    """, (clean_slug, title.strip(), summary.strip(), content.strip(), category.strip(),
          tags.strip(), author_name.strip(), 1 if is_published else 0, now, article_id))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/blog", status_code=302)

@router.post("/blog/{article_id}/delete")
def admin_blog_delete(request: Request, article_id: int):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/blog", status_code=302)

# --- Inquiries Management ---

@router.get("/inquiries", response_class=HTMLResponse)
def admin_inquiries_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contact_inquiries ORDER BY id DESC")
    inquiries = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/inquiries.html",
        context={"request": request, "user": user, "inquiries": inquiries}
    )

@router.post("/inquiries/{inquiry_id}/toggle")
def admin_inquiry_toggle(request: Request, inquiry_id: int):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE contact_inquiries SET is_resolved = CASE WHEN is_resolved = 1 THEN 0 ELSE 1 END WHERE id = ?", (inquiry_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/inquiries", status_code=302)

@router.post("/inquiries/{inquiry_id}/delete")
def admin_inquiry_delete(request: Request, inquiry_id: int):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contact_inquiries WHERE id = ?", (inquiry_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/inquiries", status_code=302)

# --- Users & Assets ---

@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, phone, first_name, last_name, is_admin, is_suspended,
           subscription_tier, subscription_expires_at, last_ip, created_at
    FROM users ORDER BY id DESC
    """)
    all_users = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={"request": request, "user": user, "users": all_users}
    )

@router.get("/assets", response_class=HTMLResponse)
def assets_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT a.*, COUNT(v.id) as version_count
    FROM assets a
    LEFT JOIN asset_versions v ON a.id = v.asset_id
    GROUP BY a.id
    ORDER BY a.updated_at DESC
    """)
    all_assets = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/assets.html",
        context={"request": request, "user": user, "assets": all_assets}
    )

@router.post("/assets/{asset_id}/delete")
def delete_asset_action(request: Request, asset_id: str):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM asset_versions WHERE asset_id = ?", (asset_id,))
    cursor.execute("DELETE FROM comments WHERE asset_id = ?", (asset_id,))
    cursor.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/assets", status_code=302)

# --- Publishing ---

@router.get("/publish", response_class=HTMLResponse)
def publish_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/publish.html",
        context={"request": request, "user": user, "success": None}
    )

@router.post("/publish", response_class=HTMLResponse)
async def publish_action(request: Request,
                         slug: str = Form(...),
                         name: str = Form(...),
                         type: str = Form(...),
                         asset_status: str = Form("stable"),
                         version: str = Form(...),
                         min_autocad: int = Form(2018),
                         short_desc: str = Form(""),
                         full_desc: str = Form(""),
                         entry_point: str = Form(...),
                         commands_json_payload: str = Form("[]"),
                         release_notes: str = Form(""),
                         is_pro: bool = Form(False),
                         tags: str = Form(""),
                         icon_file: Optional[UploadFile] = File(None),
                         source_files: List[UploadFile] = File(...),
                         media_files: List[UploadFile] = File([]),
                         media_titles: List[str] = Form([]),
                         media_descriptions: List[str] = Form([]),
                         asset_id: Optional[str] = Form(None)):
    user = require_admin(request)
    slug = slug.strip().lower()
    computed_asset_id = asset_id.strip() if (asset_id and asset_id.strip()) else PackageService.generate_asset_id(slug)

    thumb_32_url, thumb_64_url = "", ""
    if icon_file and icon_file.filename:
        thumb_32_url, thumb_64_url = PackageService.process_icon(slug, icon_file)

    media_data = PackageService.save_media_items(slug, media_files, media_titles, media_descriptions)

    try:
        commands_list = json.loads(commands_json_payload)
    except Exception:
        commands_list = []

    pkg_info = PackageService.build_package_bundle(
        slug, version.strip(), source_files, entry_point.strip(), commands_list
    )

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO assets (id, slug, name, type, asset_status, min_autocad, short_desc, full_desc,
                        thumb_32_url, thumb_64_url, is_pro, commands_json,
                        tags, media_json, latest_version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        slug=excluded.slug,
        name=excluded.name,
        type=excluded.type,
        asset_status=excluded.asset_status,
        min_autocad=excluded.min_autocad,
        short_desc=excluded.short_desc,
        full_desc=excluded.full_desc,
        thumb_32_url=COALESCE(NULLIF(excluded.thumb_32_url, ''), assets.thumb_32_url),
        thumb_64_url=COALESCE(NULLIF(excluded.thumb_64_url, ''), assets.thumb_64_url),
        is_pro=excluded.is_pro,
        commands_json=excluded.commands_json,
        tags=excluded.tags,
        media_json=CASE WHEN excluded.media_json != '[]' THEN excluded.media_json ELSE assets.media_json END,
        latest_version=excluded.latest_version,
        updated_at=excluded.updated_at
    """, (computed_asset_id, slug, name.strip(), type.strip(), asset_status.strip(), min_autocad,
          short_desc.strip(), full_desc.strip(), thumb_32_url, thumb_64_url,
          1 if is_pro else 0, json.dumps(commands_list),
          tags.strip(), json.dumps(media_data), version.strip(), now, now))

    cursor.execute("""
    INSERT OR REPLACE INTO asset_versions (asset_id, version, release_notes, download_url, file_size, sha256, commands_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (computed_asset_id, version.strip(), release_notes.strip(), pkg_info["download_url"],
          pkg_info["file_size"], pkg_info["sha256"], json.dumps(commands_list), now))

    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/publish.html",
        context={"request": request, "user": user, "success": f"Asset '{name}' (ID: {computed_asset_id}) published successfully."}
    )

# --- Plans ---

@router.get("/plans", response_class=HTMLResponse)
def plans_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscription_plans ORDER BY price_toman ASC")
    plans = cursor.fetchall()
    conn.close()

    formatted = []
    for p in plans:
        item = dict(p)
        item["features_text"] = "\n".join(json.loads(p["features_json"]) if p["features_json"] else [])
        formatted.append(item)

    return templates.TemplateResponse(
        request=request,
        name="admin/plans.html",
        context={"request": request, "user": user, "plans": formatted, "success": None}
    )
