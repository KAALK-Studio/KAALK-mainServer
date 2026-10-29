# app/routers/admin.py
import os
import json
import datetime
from typing import List, Optional
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
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

@router.get("/users/create", response_class=HTMLResponse)
def create_user_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/user_create.html",
        context={"request": request, "user": user, "error": None}
    )

@router.post("/users/create", response_class=HTMLResponse)
def create_user_action(request: Request,
                       first_name: str = Form(...),
                       last_name: str = Form(...),
                       email: str = Form(...),
                       phone: str = Form(...),
                       password: str = Form(...),
                       subscription_tier: str = Form("free"),
                       subscription_days: int = Form(0),
                       is_admin: bool = Form(False),
                       is_suspended: bool = Form(False)):
    user = require_admin(request)
    email_clean = email.strip().lower()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="admin/user_create.html",
            context={"request": request, "user": user, "error": "An account with this email already exists."}
        )

    now = datetime.datetime.utcnow().isoformat()
    new_expiry = None
    if subscription_tier == "premium" and subscription_days > 0:
        new_expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=subscription_days)).isoformat()

    hashed = hash_password(password)
    client_ip = request.client.host if request.client else "127.0.0.1"

    cursor.execute("""
    INSERT INTO users (email, phone, password_hash, first_name, last_name, is_admin, is_suspended,
                       subscription_tier, subscription_expires_at, last_ip, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (email_clean, phone.strip(), hashed, first_name.strip(), last_name.strip(),
          1 if is_admin else 0, 1 if is_suspended else 0, subscription_tier, new_expiry, client_ip, now))

    conn.commit()
    conn.close()

    return RedirectResponse("/admin/users", status_code=302)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user_page(request: Request, user_id: int):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    target_user = cursor.fetchone()
    conn.close()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    return templates.TemplateResponse(
        request=request,
        name="admin/user_edit.html",
        context={"request": request, "user": user, "target_user": target_user, "success": None}
    )

@router.post("/users/{user_id}/edit", response_class=HTMLResponse)
def update_user_action(request: Request,
                       user_id: int,
                       first_name: str = Form(...),
                       last_name: str = Form(...),
                       email: str = Form(...),
                       phone: str = Form(...),
                       subscription_tier: str = Form(...),
                       subscription_days: int = Form(0),
                       is_admin: bool = Form(False),
                       is_suspended: bool = Form(False)):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()

    new_expiry = None
    if subscription_tier == "premium" and subscription_days > 0:
        new_expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=subscription_days)).isoformat()

    cursor.execute("""
    UPDATE users SET
        first_name = ?, last_name = ?, email = ?, phone = ?,
        subscription_tier = ?, subscription_expires_at = COALESCE(?, subscription_expires_at),
        is_admin = ?, is_suspended = ?
    WHERE id = ?
    """, (first_name.strip(), last_name.strip(), email.strip().lower(), phone.strip(),
          subscription_tier, new_expiry, 1 if is_admin else 0, 1 if is_suspended else 0, user_id))

    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    updated_user = cursor.fetchone()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/user_edit.html",
        context={"request": request, "user": user, "target_user": updated_user, "success": "User profile updated successfully."}
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

@router.get("/assets/{asset_id}/edit", response_class=HTMLResponse)
def edit_asset_page(request: Request, asset_id: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    target_asset = cursor.fetchone()
    conn.close()

    if not target_asset:
        raise HTTPException(status_code=404, detail="Asset not found.")

    asset_dict = dict(target_asset)
    try:
        raw_media = json.loads(asset_dict.get("media_json") or "[]")
    except Exception:
        raw_media = []

    try:
        raw_commands = json.loads(asset_dict.get("commands_json") or "[]")
    except Exception:
        raw_commands = []

    media_items = []
    for m in raw_media:
        m_copy = dict(m)
        url = m_copy.get("media_url") or ""
        m_copy["display_filename"] = url.split('/')[-1] if url else "Media File"
        media_items.append(m_copy)

    asset_dict["media_items"] = media_items
    asset_dict["commands_list"] = raw_commands

    return templates.TemplateResponse(
        request=request,
        name="admin/asset_edit.html",
        context={"request": request, "user": user, "asset": asset_dict, "success": None}
    )

@router.post("/assets/{asset_id}/edit", response_class=HTMLResponse)
async def update_asset_action(request: Request,
                              asset_id: str,
                              name: str = Form(...),
                              type: str = Form(...),
                              asset_status: str = Form("stable"),
                              min_autocad: int = Form(2018),
                              short_desc: str = Form(""),
                              full_desc: str = Form(""),
                              commands_json_payload: str = Form("[]"),
                              tags: str = Form(""),
                              is_pro: bool = Form(False),
                              media_json_payload: str = Form("[]"),
                              icon_file: Optional[UploadFile] = File(None),
                              new_media_files: List[UploadFile] = File([]),
                              new_media_titles: List[str] = Form([]),
                              new_media_descriptions: List[str] = Form([])):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    slug = existing["slug"]
    thumb_32 = existing["thumb_32_url"]
    thumb_64 = existing["thumb_64_url"]

    if icon_file and icon_file.filename:
        thumb_32, thumb_64 = PackageService.process_icon(slug, icon_file)

    try:
        updated_media = json.loads(media_json_payload)
    except Exception:
        updated_media = []

    try:
        updated_commands = json.loads(commands_json_payload)
    except Exception:
        updated_commands = []

    if new_media_files and len(new_media_files) > 0 and new_media_files[0].filename:
        added_media = PackageService.save_media_items(slug, new_media_files, new_media_titles, new_media_descriptions)
        updated_media.extend(added_media)

    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE assets SET
        name = ?, type = ?, asset_status = ?, min_autocad = ?,
        short_desc = ?, full_desc = ?, commands_json = ?,
        tags = ?, is_pro = ?, thumb_32_url = ?, thumb_64_url = ?,
        media_json = ?, updated_at = ?
    WHERE id = ?
    """, (name.strip(), type.strip(), asset_status.strip(), min_autocad,
          short_desc.strip(), full_desc.strip(), json.dumps(updated_commands),
          tags.strip(), 1 if is_pro else 0, thumb_32, thumb_64,
          json.dumps(updated_media), now, asset_id))

    conn.commit()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    updated_asset = dict(cursor.fetchone())
    conn.close()

    media_items = []
    for m in updated_media:
        m_copy = dict(m)
        url = m_copy.get("media_url") or ""
        m_copy["display_filename"] = url.split('/')[-1] if url else "Media File"
        media_items.append(m_copy)

    updated_asset["media_items"] = media_items
    updated_asset["commands_list"] = updated_commands

    return templates.TemplateResponse(
        request=request,
        name="admin/asset_edit.html",
        context={"request": request, "user": user, "asset": updated_asset, "success": "Asset updated successfully."}
    )

@router.get("/assets/{asset_id}/versions", response_class=HTMLResponse)
def asset_versions_page(request: Request, asset_id: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (asset_id,))
    versions = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/versions.html",
        context={"request": request, "user": user, "asset": asset, "versions": versions}
    )

@router.post("/assets/{asset_id}/versions/{version}/delete")
def delete_asset_version(request: Request, asset_id: str, version: str):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()

    cursor.execute("DELETE FROM asset_versions WHERE asset_id = ? AND version = ?", (asset_id, version))
    cursor.execute("SELECT version FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (asset_id,))
    remaining = [r["version"] for r in cursor.fetchall()]

    new_latest = remaining[0] if remaining else ""
    cursor.execute("UPDATE assets SET latest_version = ? WHERE id = ?", (new_latest, asset_id))
    conn.commit()
    conn.close()

    PackageService.delete_version_archive(asset["slug"], version, remaining)
    return RedirectResponse(f"/admin/assets/{asset_id}/versions", status_code=302)

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
                         commands_json_payload: str = Form("[]"),
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
    """, (asset_id.strip(), slug, name.strip(), type.strip(), asset_status.strip(), min_autocad,
          short_desc.strip(), full_desc.strip(), thumb_32_url, thumb_64_url,
          1 if is_pro else 0, json.dumps(commands_list),
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
        context={"request": request, "user": user, "success": f"Asset '{name}' published successfully."}
    )

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
        context={"request": request, "user": user, "plans": formatted, "success": f"Plan '{name}' successfully updated."}
    )

@router.get("/reviews", response_class=HTMLResponse)
def reviews_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.id, c.asset_id, c.author, c.text, c.rating, c.created_at, COALESCE(a.name, c.asset_id) as asset_name
    FROM comments c
    LEFT JOIN assets a ON c.asset_id = a.id
    ORDER BY c.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    formatted_comments = []
    for r in rows:
        item = dict(r)
        item["created_at_short"] = str(item.get("created_at") or "")[:10]
        r_val = item.get("rating")
        try:
            item["rating_int"] = int(r_val) if (r_val is not None and int(r_val) > 0) else None
        except (ValueError, TypeError):
            item["rating_int"] = None
        formatted_comments.append(item)

    return templates.TemplateResponse(
        request=request,
        name="admin/reviews.html",
        context={"request": request, "user": user, "comments": formatted_comments}
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
