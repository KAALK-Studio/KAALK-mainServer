import os
import json
import datetime
from typing import List, Optional
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.security import get_current_user_from_cookie
from app.services.package_service import PackageService

templates = Jinja2Templates(directory="app/templates")
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

    # 1. User & Pro Counts
    cursor.execute("SELECT COUNT(*) as c FROM users")
    total_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE subscription_tier = 'premium'")
    pro_users = cursor.fetchone()["c"]

    # 2. Timeframe Growth (24h, 7d, 30d)
    now = datetime.datetime.utcnow()
    d1 = (now - datetime.timedelta(days=1)).isoformat()
    d7 = (now - datetime.timedelta(days=7)).isoformat()
    d30 = (now - datetime.timedelta(days=30)).isoformat()

    def get_growth(since_date):
        cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN subscription_tier='premium' THEN 1 ELSE 0 END) as pro FROM users WHERE created_at >= ?", (since_date,))
        row = cursor.fetchone()
        tot = row["total"] or 0
        pro = row["pro"] or 0
        return tot - pro, pro, tot

    day_free, day_pro, day_total = get_growth(d1)
    week_free, week_pro, week_total = get_growth(d7)
    month_free, month_pro, month_total = get_growth(d30)

    # 3. Monthly Revenue
    month_start = datetime.datetime(now.year, now.month, 1).isoformat()
    cursor.execute("SELECT SUM(amount_toman) as rev FROM payments WHERE status = 'completed' AND completed_at >= ?", (month_start,))
    monthly_revenue = cursor.fetchone()["rev"] or 0

    # 4. Total and Monthly Downloads
    cursor.execute("SELECT COUNT(*) as c, SUM(download_count) as total_dl, SUM(monthly_downloads) as m_dl FROM assets")
    asset_stat = cursor.fetchone()
    total_assets = asset_stat["c"] or 0
    monthly_downloads = asset_stat["m_dl"] or 0

    # 5. Top and Low Assets
    cursor.execute("SELECT name, download_count, rating, rating_count FROM assets ORDER BY download_count DESC LIMIT 1")
    top_asset = cursor.fetchone()

    cursor.execute("SELECT name, rating, rating_count FROM assets WHERE rating_count > 0 ORDER BY rating ASC LIMIT 1")
    low_asset = cursor.fetchone()

    # 6. Geo Nodes for User IP Visualization
    cursor.execute("SELECT DISTINCT last_ip FROM users LIMIT 30")
    ip_rows = cursor.fetchall()
    geo_nodes = []
    # Seed reproducible stylized positions on map canvas for distinct user IPs
    for idx, r in enumerate(ip_rows):
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
            "user": user, "total_users": total_users, "pro_users": pro_users,
            "total_assets": total_assets, "monthly_revenue": monthly_revenue,
            "monthly_downloads": monthly_downloads, "growth": growth,
            "top_asset": top_asset, "low_asset": low_asset, "geo_nodes": geo_nodes
        }
    )

# --- User Management ---

@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, phone, first_name, last_name, is_admin, is_suspended, subscription_tier, last_ip, created_at FROM users ORDER BY id DESC")
    all_users = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={"user": user, "users": all_users}
    )

@router.post("/users/{user_id}/delete")
def delete_user_action(request: Request, user_id: int):
    user = require_admin(request)
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your active admin account.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM comments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/users", status_code=302)

# --- Asset Publishing & Management ---

@router.get("/publish", response_class=HTMLResponse)
def publish_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(request=request, name="admin/publish.html", context={"user": user, "success": None})

@router.post("/publish", response_class=HTMLResponse)
async def publish_action(request: Request,
                         asset_id: str = Form(...),
                         slug: str = Form(...),
                         name: str = Form(...),
                         type: str = Form(...),
                         asset_status: str = Form("stable"),
                         version: str = Form(...),
                         min_autocad: int = Form(2018),
                         short_desc: str = Form(""),
                         full_desc: str = Form(""),
                         entry_point: str = Form(...),
                         default_command: str = Form(""),
                         default_alias: str = Form(""),
                         release_notes: str = Form(""),
                         is_pro: bool = Form(False),
                         tags: str = Form(""),
                         icon_file: Optional[UploadFile] = File(None),
                         source_files: List[UploadFile] = File(...),
                         media_files: List[UploadFile] = File([]),
                         media_titles: List[str] = Form([]),
                         media_descriptions: List[str] = Form([])):
    user = require_admin(request)
    slug = slug.strip().lower()

    thumb_32_url, thumb_64_url = "", ""
    if icon_file and icon_file.filename:
        thumb_32_url, thumb_64_url = PackageService.process_icon(slug, icon_file)

    media_data = PackageService.save_media_items(slug, media_files, media_titles, media_descriptions)

    pkg_info = PackageService.build_package_bundle(
        slug, version.strip(), source_files, entry_point.strip(), default_command.strip(), default_alias.strip()
    )

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO assets (id, slug, name, type, asset_status, min_autocad, short_desc, full_desc,
                        thumb_32_url, thumb_64_url, is_pro, default_command, default_alias,
                        tags, media_json, latest_version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        default_command=excluded.default_command,
        default_alias=excluded.default_alias,
        tags=excluded.tags,
        media_json=CASE WHEN excluded.media_json != '[]' THEN excluded.media_json ELSE assets.media_json END,
        latest_version=excluded.latest_version,
        updated_at=excluded.updated_at
    """, (asset_id.strip(), slug, name.strip(), type.strip(), asset_status.strip(), min_autocad,
          short_desc.strip(), full_desc.strip(), thumb_32_url, thumb_64_url,
          1 if is_pro else 0, default_command.strip(), default_alias.strip(),
          tags.strip(), json.dumps(media_data), version.strip(), now, now))

    cursor.execute("""
    INSERT OR REPLACE INTO asset_versions (asset_id, version, release_notes, download_url, file_size, sha256, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (asset_id.strip(), version.strip(), release_notes.strip(), pkg_info["download_url"],
          pkg_info["file_size"], pkg_info["sha256"], now))

    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/publish.html",
        context={"user": user, "success": f"Asset '{name}' (Status: {asset_status.upper()}) Version {version} compiled successfully with entry point '{entry_point}'."}
    )

# --- Plans Management (Replaces Pricing for Admins) ---

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
        context={"user": user, "plans": formatted, "success": None}
    )

@router.post("/plans/{plan_id}", response_class=HTMLResponse)
def update_plan_action(request: Request,
                       plan_id: str,
                       name: str = Form(...),
                       price_toman: int = Form(...),
                       duration_days: int = Form(...),
                       billing_cycle: str = Form(...),
                       discount_percent: int = Form(0),
                       discount_badge: str = Form(""),
                       discount_expires_at: Optional[str] = Form(None),
                       description: str = Form(""),
                       features: str = Form(...),
                       is_active: bool = Form(False)):
    user = require_admin(request)
    features_list = [f.strip() for f in features.splitlines() if f.strip()]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE subscription_plans
    SET name = ?, price_toman = ?, duration_days = ?, billing_cycle = ?,
        discount_percent = ?, discount_badge = ?, discount_expires_at = ?,
        description = ?, features_json = ?, is_active = ?
    WHERE id = ?
    """, (name.strip(), price_toman, duration_days, billing_cycle.strip(),
          discount_percent, discount_badge.strip(), discount_expires_at.strip() if discount_expires_at else None,
          description.strip(), json.dumps(features_list), 1 if is_active else 0, plan_id))
    conn.commit()

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
        context={"user": user, "plans": formatted, "success": f"Plan '{name}' successfully updated."}
    )

# --- Reviews & Ratings Management ---

@router.get("/reviews", response_class=HTMLResponse)
def reviews_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.*, a.name as asset_name
    FROM comments c
    JOIN assets a ON c.asset_id = a.id
    ORDER BY c.id DESC
    """)
    comments = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/reviews.html",
        context={"user": user, "comments": comments}
    )

@router.post("/reviews/{comment_id}/delete")
def delete_review(request: Request, comment_id: int):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/reviews", status_code=302)