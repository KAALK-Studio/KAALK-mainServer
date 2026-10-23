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
    cursor.execute("SELECT COUNT(*) as c FROM users")
    user_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM assets")
    asset_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE subscription_tier = 'premium'")
    pro_count = cursor.fetchone()["c"]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={"user": user, "user_count": user_count, "asset_count": asset_count, "pro_count": pro_count}
    )

# --- User Management (Edit, Suspend, Grant Admin, Adjust Subscriptions) ---

@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, first_name, last_name, is_admin, is_suspended,
           subscription_tier, subscription_expires_at, created_at
    FROM users ORDER BY id DESC
    """)
    all_users = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={"user": user, "users": all_users}
    )

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
        context={"user": user, "target_user": target_user, "success": None}
    )

@router.post("/users/{user_id}/edit", response_class=HTMLResponse)
def update_user_action(request: Request,
                       user_id: int,
                       first_name: str = Form(...),
                       last_name: str = Form(...),
                       email: str = Form(...),
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
        first_name = ?, last_name = ?, email = ?,
        subscription_tier = ?, subscription_expires_at = ?,
        is_admin = ?, is_suspended = ?
    WHERE id = ?
    """, (first_name.strip(), last_name.strip(), email.strip().lower(),
          subscription_tier, new_expiry, 1 if is_admin else 0, 1 if is_suspended else 0, user_id))

    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    updated_user = cursor.fetchone()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/user_edit.html",
        context={"user": user, "target_user": updated_user, "success": "User profile and credentials updated successfully."}
    )

@router.post("/users/{user_id}/delete")
def delete_user_action(request: Request, user_id: int):
    user = require_admin(request)
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own active admin account.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM comments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/users", status_code=302)

# --- Asset Management & Multi-file Deployment ---

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
        context={"user": user, "assets": all_assets}
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
        context={"user": user, "asset": asset, "versions": versions}
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

@router.get("/publish", response_class=HTMLResponse)
def publish_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/publish.html",
        context={"user": user, "success": None}
    )

@router.post("/publish", response_class=HTMLResponse)
async def publish_action(request: Request,
                         asset_id: str = Form(...),
                         slug: str = Form(...),
                         name: str = Form(...),
                         type: str = Form(...),
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

    # 1. Process Icon into 32x32 and 64x64
    thumb_32_url, thumb_64_url = "", ""
    if icon_file and icon_file.filename:
        thumb_32_url, thumb_64_url = PackageService.process_icon(slug, icon_file)

    # 2. Process Media with individual title and description
    media_data = PackageService.save_media_items(slug, media_files, media_titles, media_descriptions)

    # 3. Build bundle with multiple source files + package.json
    pkg_info = PackageService.build_package_bundle(
        slug, version.strip(), source_files, entry_point.strip(), default_command.strip(), default_alias.strip()
    )

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO assets (id, slug, name, type, min_autocad, short_desc, full_desc,
                        thumb_32_url, thumb_64_url, is_pro, default_command, default_alias,
                        tags, media_json, latest_version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        slug=excluded.slug,
        name=excluded.name,
        type=excluded.type,
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
    """, (asset_id.strip(), slug, name.strip(), type.strip(), min_autocad,
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
        context={"user": user, "success": f"Package bundle for '{name}' version {version} compiled and published successfully."}
    )

# --- Pricing and Plan Administration ---

@router.get("/pricing", response_class=HTMLResponse)
def admin_pricing_page(request: Request):
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
        name="admin/pricing.html",
        context={"user": user, "plans": formatted, "success": None}
    )

@router.post("/pricing", response_class=HTMLResponse)
def update_pricing_plan(request: Request,
                        plan_id: str = Form(...),
                        name: str = Form(...),
                        price_toman: int = Form(...),
                        duration_days: int = Form(...),
                        billing_cycle: str = Form(...),
                        discount_badge: str = Form(""),
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
        discount_badge = ?, description = ?, features_json = ?, is_active = ?
    WHERE id = ?
    """, (name.strip(), price_toman, duration_days, billing_cycle.strip(),
          discount_badge.strip(), description.strip(), json.dumps(features_list),
          1 if is_active else 0, plan_id.strip()))
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
        name="admin/pricing.html",
        context={"user": user, "plans": formatted, "success": f"Plan '{name}' successfully updated."}
    )