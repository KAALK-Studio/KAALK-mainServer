# app/routers/admin.py
import os
import json
import datetime
import re
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from app.config import DOWNLOADS_DIR, BLOG_DIR, MAILDIR_PATH, SMTP_HOST, SMTP_PORT, SMTP_FROM
from app.database import get_db
from app.security import hash_password, get_current_user_from_cookie
from app.services.package_service import PackageService
from app.services.mail_service import MailService
from app.templates_config import templates

router = APIRouter(prefix="/admin", tags=["Admin Panel"])

def require_admin(request: Request):
    user = get_current_user_from_cookie(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user

def normalize_commands_payload(raw_payload: str) -> List[dict]:
    try:
        commands_list = json.loads(raw_payload) if raw_payload else []
    except Exception:
        commands_list = []

    normalized = []
    for cmd in commands_list:
        if isinstance(cmd, dict) and cmd.get("command"):
            clean_cmd = str(cmd.get("command", "")).strip().upper()
            raw_alias = str(cmd.get("alias", "")).strip().upper()
            alias_parts = [p.strip() for p in re.split(r"[,;]+", raw_alias) if p.strip()]
            normalized_alias = ", ".join(alias_parts)

            if clean_cmd:
                normalized.append({
                    "command": clean_cmd,
                    "alias": normalized_alias,
                    "title": str(cmd.get("title", "")).strip(),
                    "status": str(cmd.get("status", "stable")).strip().lower(),
                    "description": str(cmd.get("description", "")).strip(),
                    "deprecation_notice": str(cmd.get("deprecation_notice", "")).strip()
                })
    return normalized

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

# ----------------- HOME PAGE CMS EDITOR -----------------
@router.get("/home", response_class=HTMLResponse)
def admin_home_cms_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT content_json FROM site_content WHERE key = 'home'")
    row = cursor.fetchone()
    conn.close()

    content = json.loads(row["content_json"]) if row else {}
    return templates.TemplateResponse(
        request=request,
        name="admin/home_edit.html",
        context={"request": request, "user": user, "content": content, "success": None}
    )

@router.post("/home", response_class=HTMLResponse)
def admin_home_cms_action(request: Request,
                          hero_title: str = Form(...),
                          hero_subtitle: str = Form(...),
                          cta_download_text: str = Form("Download Plugin Installer"),
                          cta_pricing_text: str = Form("Explore Pro Plans"),
                          announcement_badge: str = Form(""),
                          announcement_title: str = Form(""),
                          announcement_desc: str = Form(""),
                          announcement_link: str = Form(""),
                          featured_tool_title: str = Form(""),
                          featured_tool_desc: str = Form(""),
                          featured_tool_link: str = Form(""),
                          feature1_title: str = Form("Zero AutoCAD Restarts"),
                          feature1_desc: str = Form(""),
                          feature2_title: str = Form("Two-Tier Catalog Manifests"),
                          feature2_desc: str = Form(""),
                          feature3_title: str = Form("AutoCAD PGP Synchronization"),
                          feature3_desc: str = Form("")):
    user = require_admin(request)
    data = {
        "hero_title": hero_title.strip(),
        "hero_subtitle": hero_subtitle.strip(),
        "cta_download_text": cta_download_text.strip(),
        "cta_pricing_text": cta_pricing_text.strip(),
        "announcement_badge": announcement_badge.strip(),
        "announcement_title": announcement_title.strip(),
        "announcement_desc": announcement_desc.strip(),
        "announcement_link": announcement_link.strip(),
        "featured_tool_title": featured_tool_title.strip(),
        "featured_tool_desc": featured_tool_desc.strip(),
        "featured_tool_link": featured_tool_link.strip(),
        "feature1_title": feature1_title.strip(),
        "feature1_desc": feature1_desc.strip(),
        "feature2_title": feature2_title.strip(),
        "feature2_desc": feature2_desc.strip(),
        "feature3_title": feature3_title.strip(),
        "feature3_desc": feature3_desc.strip()
    }

    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO site_content (key, content_json, updated_at) VALUES ('home', ?, ?)
    ON CONFLICT(key) DO UPDATE SET content_json = excluded.content_json, updated_at = excluded.updated_at
    """, (json.dumps(data), now))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/home_edit.html",
        context={"request": request, "user": user, "content": data, "success": "Home page content updated successfully."}
    )

# ----------------- ABOUT PAGE CMS EDITOR -----------------
@router.get("/content/about", response_class=HTMLResponse)
@router.get("/about", response_class=HTMLResponse)
def admin_about_cms_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT content_json FROM site_content WHERE key = 'about'")
    row = cursor.fetchone()
    conn.close()

    content = json.loads(row["content_json"]) if row else {}
    return templates.TemplateResponse(
        request=request,
        name="admin/about_edit.html",
        context={"request": request, "user": user, "content": content, "success": None}
    )

@router.post("/content/about", response_class=HTMLResponse)
@router.post("/about", response_class=HTMLResponse)
def admin_about_cms_action(request: Request,
                           title: str = Form(...),
                           mission: str = Form(...),
                           story: str = Form(...),
                           team_json_payload: str = Form("[]")):
    user = require_admin(request)
    try:
        team_list = json.loads(team_json_payload) if team_json_payload else []
    except Exception:
        team_list = []

    clean_team = []
    for m in team_list:
        if isinstance(m, dict) and m.get("name") and m.get("role"):
            clean_team.append({
                "name": str(m["name"]).strip(),
                "role": str(m["role"]).strip(),
                "bio": str(m.get("bio", "")).strip()
            })

    data = {
        "title": title.strip(),
        "mission": mission.strip(),
        "story": story.strip(),
        "team": clean_team
    }

    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO site_content (key, content_json, updated_at) VALUES ('about', ?, ?)
    ON CONFLICT(key) DO UPDATE SET content_json = excluded.content_json, updated_at = excluded.updated_at
    """, (json.dumps(data), now))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/about_edit.html",
        context={"request": request, "user": user, "content": data, "success": "About page content updated successfully."}
    )

# ----------------- UNIVERSAL CMS FALLBACK ROUTE -----------------
@router.get("/content/{page_key}", response_class=HTMLResponse)
def admin_content_fallback_page(request: Request, page_key: str):
    if page_key == "home":
        return RedirectResponse("/admin/home", status_code=302)
    if page_key == "about":
        return RedirectResponse("/admin/content/about", status_code=302)

    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM site_content WHERE key = ?", (page_key,))
    row = cursor.fetchone()
    conn.close()

    content_data = json.loads(row["content_json"]) if row else {}
    return templates.TemplateResponse(
        request=request,
        name="admin/content_edit.html",
        context={"request": request, "user": user, "page_key": page_key, "content_json": json.dumps(content_data, indent=2), "success": None}
    )

@router.post("/content/{page_key}", response_class=HTMLResponse)
def admin_content_fallback_action(request: Request, page_key: str, content_json_raw: str = Form(...)):
    user = require_admin(request)
    try:
        parsed = json.loads(content_json_raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO site_content (key, content_json, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET content_json = excluded.content_json, updated_at = excluded.updated_at
    """, (page_key, json.dumps(parsed), now))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/content_edit.html",
        context={"request": request, "user": user, "page_key": page_key, "content_json": json.dumps(parsed, indent=2), "success": f"Content for '{page_key}' updated successfully."}
    )

# ----------------- ADMIN MAILBOX & TICKETS -----------------
@router.get("/mailbox", response_class=HTMLResponse)
def admin_mailbox_page(request: Request, folder: str = Query("inbox"), success: Optional[str] = Query(None)):
    user = require_admin(request)
    current_folder = folder.lower().strip()
    if current_folder not in ["inbox", "sent", "trash", "tickets"]:
        current_folder = "inbox"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contact_tickets ORDER BY id DESC")
    all_tickets = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as c FROM contact_tickets WHERE status = 'open'")
    open_tickets_count = cursor.fetchone()["c"]
    conn.close()

    unread_mail_count = MailService.get_unread_count()
    messages = []
    if current_folder != "tickets":
        messages = MailService.list_folder_messages(current_folder)

    return templates.TemplateResponse(
        request=request,
        name="admin/mailbox.html",
        context={
            "request": request,
            "user": user,
            "current_folder": current_folder,
            "messages": messages,
            "tickets": all_tickets,
            "unread_mail_count": unread_mail_count,
            "open_tickets_count": open_tickets_count,
            "smtp_info": f"{SMTP_HOST}:{SMTP_PORT}",
            "maildir_display": MailService.get_maildir_path(),
            "success": success
        }
    )

@router.get("/mailbox/view/{folder}/{msg_id}")
def admin_mailbox_view_message(request: Request, folder: str, msg_id: str):
    require_admin(request)
    msg_data = MailService.read_message(folder, msg_id)
    if not msg_data:
        return JSONResponse({"error": "Message not found."}, status_code=404)
    return JSONResponse(msg_data)

@router.post("/mailbox/send")
def admin_mailbox_send(request: Request,
                       to_address: str = Form(...),
                       subject: str = Form(...),
                       body_text: str = Form(...),
                       reply_to_id: Optional[str] = Form(None),
                       ticket_id: Optional[int] = Form(None)):
    require_admin(request)
    try:
        MailService.send_email(to_address.strip(), subject.strip(), body_text.strip(), reply_to_id)
        if ticket_id:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE contact_tickets SET status = 'answered' WHERE id = ?", (ticket_id,))
            conn.commit()
            conn.close()
        return RedirectResponse("/admin/mailbox?folder=sent&success=Email+dispatched+successfully", status_code=302)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(ex)}")

@router.post("/mailbox/delete")
def admin_mailbox_delete(request: Request, folder: str = Form(...), msg_id: str = Form(...)):
    require_admin(request)
    MailService.move_to_trash(folder, msg_id)
    return RedirectResponse(f"/admin/mailbox?folder={folder}&success=Item+processed", status_code=302)

@router.post("/mailbox/empty-trash")
def admin_mailbox_empty_trash(request: Request):
    require_admin(request)
    count = MailService.empty_trash()
    return RedirectResponse(f"/admin/mailbox?folder=trash&success=Purged+{count}+items+permanently", status_code=302)

@router.get("/mailbox/api/status")
def admin_mailbox_status_api(request: Request):
    require_admin(request)
    unread = MailService.get_unread_count()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM contact_tickets WHERE status = 'open'")
    open_tickets = cursor.fetchone()["c"]
    conn.close()
    return JSONResponse({
        "unread_mail_count": unread,
        "open_tickets_count": open_tickets,
        "total_attention_required": unread + open_tickets
    })

@router.post("/mailbox/ticket/{ticket_id}/delete")
def admin_mailbox_delete_ticket(request: Request, ticket_id: int):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contact_tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/mailbox?folder=tickets&success=Ticket+removed", status_code=302)

# ----------------- ASSET EXPORT & IMPORT (COMPLETE BUNDLE) -----------------
@router.get("/assets/{asset_id}/export")
def export_asset_action(request: Request, asset_id: str):
    require_admin(request)
    bundle_path, bundle_filename = PackageService.export_asset_bundle(asset_id)
    return FileResponse(
        path=bundle_path,
        filename=bundle_filename,
        media_type="application/zip"
    )

@router.post("/assets/import")
async def import_asset_action(request: Request, bundle_file: UploadFile = File(...)):
    require_admin(request)
    if not bundle_file or not bundle_file.filename:
        raise HTTPException(status_code=400, detail="Please select a valid .zip bundle to import.")

    success, asset_name = PackageService.import_asset_bundle(bundle_file)
    return RedirectResponse(f"/admin/assets?success=Asset+{asset_name}+imported+successfully+with+all+versions", status_code=302)

# ----------------- DOWNLOADS MANAGEMENT -----------------
@router.get("/downloads", response_class=HTMLResponse)
def admin_downloads_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM download_items ORDER BY id DESC")
    items = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/downloads.html",
        context={"request": request, "user": user, "downloads": items, "success": None}
    )

@router.post("/downloads/create")
async def admin_download_create_action(request: Request,
                                      title: str = Form(...),
                                      version: str = Form(...),
                                      file_type: str = Form("exe"),
                                      description: str = Form(""),
                                      direct_url: str = Form(""),
                                      installer_file: Optional[UploadFile] = File(None)):
    user = require_admin(request)
    file_url = direct_url.strip()
    file_size = 0

    if installer_file and installer_file.filename:
        uid = uuid.uuid4().hex[:8]
        safe_name = f"{uid}_{installer_file.filename}"
        dest_path = os.path.join(DOWNLOADS_DIR, safe_name)
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(installer_file.file, buffer)
        file_size = os.path.getsize(dest_path)
        file_url = f"/static/downloads/{safe_name}"

    if not file_url:
        raise HTTPException(status_code=400, detail="Either an installer file or direct URL must be provided.")

    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO download_items (title, version, file_url, file_size, file_type, description, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (title.strip(), version.strip(), file_url, file_size, file_type.strip(), description.strip(), now))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/downloads", status_code=302)

@router.post("/downloads/{item_id}/delete")
def admin_download_delete_action(request: Request, item_id: int):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM download_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/downloads", status_code=302)

# ----------------- BLOG POSTS MANAGEMENT -----------------
@router.get("/blog", response_class=HTMLResponse)
def admin_blog_list_page(request: Request):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts ORDER BY id DESC")
    posts = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/blog_list.html",
        context={"request": request, "user": user, "posts": posts}
    )

@router.get("/blog/new", response_class=HTMLResponse)
def admin_blog_create_page(request: Request):
    user = require_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/blog_edit.html",
        context={"request": request, "user": user, "post": None, "error": None}
    )

@router.post("/blog/new")
async def admin_blog_create_action(request: Request,
                                   title: str = Form(...),
                                   slug: str = Form(...),
                                   summary: str = Form(""),
                                   content: str = Form(...),
                                   video_url: str = Form(""),
                                   model_3d_url: str = Form(""),
                                   author: str = Form("KAALK Architecture Studio"),
                                   is_published: bool = Form(True),
                                   cover_file: Optional[UploadFile] = File(None),
                                   model_file: Optional[UploadFile] = File(None)):
    user = require_admin(request)
    clean_slug = slug.strip().lower()
    cover_image_url = ""
    resolved_3d_url = model_3d_url.strip()

    if cover_file and cover_file.filename:
        uid = uuid.uuid4().hex[:8]
        cover_name = f"cover_{uid}_{cover_file.filename}"
        cover_path = os.path.join(BLOG_DIR, cover_name)
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(cover_file.file, buffer)
        cover_image_url = f"/static/blog/{cover_name}"

    if model_file and model_file.filename:
        uid = uuid.uuid4().hex[:8]
        model_name = f"model_{uid}_{model_file.filename}"
        model_path = os.path.join(BLOG_DIR, model_name)
        with open(model_path, "wb") as buffer:
            shutil.copyfileobj(model_file.file, buffer)
        resolved_3d_url = f"/static/blog/{model_name}"

    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO blog_posts (slug, title, summary, content, cover_image_url, gallery_json, video_url, model_3d_url, author, is_published, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)
    """, (clean_slug, title.strip(), summary.strip(), content.strip(), cover_image_url, video_url.strip(), resolved_3d_url, author.strip(), 1 if is_published else 0, now, now))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/blog", status_code=302)

@router.get("/blog/{post_id}/edit", response_class=HTMLResponse)
def admin_blog_edit_page(request: Request, post_id: int):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    conn.close()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")

    return templates.TemplateResponse(
        request=request,
        name="admin/blog_edit.html",
        context={"request": request, "user": user, "post": dict(post), "error": None}
    )

@router.post("/blog/{post_id}/edit")
async def admin_blog_edit_action(request: Request,
                                 post_id: int,
                                 title: str = Form(...),
                                 slug: str = Form(...),
                                 summary: str = Form(""),
                                 content: str = Form(...),
                                 video_url: str = Form(""),
                                 model_3d_url: str = Form(""),
                                 author: str = Form("KAALK Architecture Studio"),
                                 is_published: bool = Form(True),
                                 cover_file: Optional[UploadFile] = File(None),
                                 model_file: Optional[UploadFile] = File(None)):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found.")

    cover_image_url = existing["cover_image_url"]
    resolved_3d_url = model_3d_url.strip() if model_3d_url.strip() else existing["model_3d_url"]

    if cover_file and cover_file.filename:
        uid = uuid.uuid4().hex[:8]
        cover_name = f"cover_{uid}_{cover_file.filename}"
        cover_path = os.path.join(BLOG_DIR, cover_name)
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(cover_file.file, buffer)
        cover_image_url = f"/static/blog/{cover_name}"

    if model_file and model_file.filename:
        uid = uuid.uuid4().hex[:8]
        model_name = f"model_{uid}_{model_file.filename}"
        model_path = os.path.join(BLOG_DIR, model_name)
        with open(model_path, "wb") as buffer:
            shutil.copyfileobj(model_file.file, buffer)
        resolved_3d_url = f"/static/blog/{model_name}"

    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE blog_posts SET
        slug = ?, title = ?, summary = ?, content = ?,
        cover_image_url = ?, video_url = ?, model_3d_url = ?,
        author = ?, is_published = ?, updated_at = ?
    WHERE id = ?
    """, (slug.strip().lower(), title.strip(), summary.strip(), content.strip(),
          cover_image_url, video_url.strip(), resolved_3d_url,
          author.strip(), 1 if is_published else 0, now, post_id))
    conn.commit()
    conn.close()

    return RedirectResponse("/admin/blog", status_code=302)

@router.post("/blog/{post_id}/delete")
def admin_blog_delete_action(request: Request, post_id: int):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/blog", status_code=302)

# ----------------- USERS & ASSETS MANAGEMENT -----------------
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
def assets_list(request: Request, success: Optional[str] = Query(None)):
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
        context={"request": request, "user": user, "assets": all_assets, "success": success}
    )

@router.get("/assets/{asset_id}/edit", response_class=HTMLResponse)
def edit_asset_page(request: Request, asset_id: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    target_asset = cursor.fetchone()
    if not target_asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = target_asset["id"]
    cursor.execute("""
    SELECT version, release_notes, download_url, file_size, sha256 
    FROM asset_versions 
    WHERE asset_id = ? AND version = ?
    """, (actual_id, target_asset["latest_version"] or ""))
    latest_ver_row = cursor.fetchone()
    conn.close()

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
    asset_dict["active_release_notes"] = latest_ver_row["release_notes"] if latest_ver_row else ""

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
                              active_release_notes: str = Form(""),
                              icon_file: Optional[UploadFile] = File(None),
                              new_media_files: List[UploadFile] = File([]),
                              new_media_titles: List[str] = Form([]),
                              new_media_descriptions: List[str] = Form([]),
                              replacement_source_files: List[UploadFile] = File([]),
                              replacement_entry_point: str = Form("")):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = existing["id"]
    slug = existing["slug"]
    thumb_32 = existing["thumb_32_url"]
    thumb_64 = existing["thumb_64_url"]
    current_latest_version = existing["latest_version"] or "0.1.0"

    if icon_file and icon_file.filename:
        thumb_32, thumb_64 = PackageService.process_icon(slug, icon_file)

    try:
        updated_media = json.loads(media_json_payload)
    except Exception:
        updated_media = []

    updated_commands = normalize_commands_payload(commands_json_payload)

    if new_media_files and len(new_media_files) > 0 and new_media_files[0].filename:
        added_media = PackageService.save_media_items(slug, new_media_files, new_media_titles, new_media_descriptions)
        updated_media.extend(added_media)

    has_replacement_files = replacement_source_files and any(f.filename for f in replacement_source_files)
    if has_replacement_files or (existing["commands_json"] != json.dumps(updated_commands)):
        pkg_res = PackageService.update_version_package(
            slug=slug,
            old_version=current_latest_version,
            new_version=current_latest_version,
            files=replacement_source_files if has_replacement_files else None,
            entry_point=replacement_entry_point,
            commands=updated_commands,
            asset_name=name.strip(),
            is_latest=True
        )
        cursor.execute("""
        UPDATE asset_versions SET
            release_notes = ?,
            download_url = ?,
            file_size = ?,
            sha256 = ?,
            commands_json = ?
        WHERE asset_id = ? AND version = ?
        """, (active_release_notes.strip(), pkg_res["download_url"], pkg_res["file_size"], pkg_res["sha256"], json.dumps(updated_commands), actual_id, current_latest_version))
    else:
        cursor.execute("""
        UPDATE asset_versions SET
            release_notes = ?,
            commands_json = ?
        WHERE asset_id = ? AND version = ?
        """, (active_release_notes.strip(), json.dumps(updated_commands), actual_id, current_latest_version))

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
          json.dumps(updated_media), now, actual_id))

    conn.commit()
    cursor.execute("SELECT * FROM assets WHERE id = ?", (actual_id,))
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
    updated_asset["active_release_notes"] = active_release_notes.strip()

    return templates.TemplateResponse(
        request=request,
        name="admin/asset_edit.html",
        context={"request": request, "user": user, "asset": updated_asset, "success": "Asset and active version package updated successfully."}
    )

@router.get("/assets/{asset_id}/versions", response_class=HTMLResponse)
def asset_versions_page(request: Request, asset_id: str, success: Optional[str] = Query(None)):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]
    cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (actual_id,))
    versions = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin/versions.html",
        context={"request": request, "user": user, "asset": asset, "versions": versions, "success": success}
    )

@router.get("/assets/{asset_id}/versions/new", response_class=HTMLResponse)
def deploy_version_page(request: Request, asset_id: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()

    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]
    cursor.execute("SELECT commands_json FROM asset_versions WHERE asset_id = ? ORDER BY id DESC LIMIT 1", (actual_id,))
    latest_ver = cursor.fetchone()
    conn.close()

    raw_commands = []
    if latest_ver and latest_ver["commands_json"]:
        try:
            raw_commands = json.loads(latest_ver["commands_json"])
        except Exception:
            raw_commands = []
    elif asset["commands_json"]:
        try:
            raw_commands = json.loads(asset["commands_json"])
        except Exception:
            raw_commands = []

    asset_dict = dict(asset)
    asset_dict["commands_list"] = raw_commands

    return templates.TemplateResponse(
        request=request,
        name="admin/version_deploy.html",
        context={"request": request, "user": user, "asset": asset_dict, "error": None}
    )

@router.post("/assets/{asset_id}/versions/new", response_class=HTMLResponse)
async def deploy_version_action(request: Request,
                                asset_id: str,
                                version: str = Form(...),
                                release_notes: str = Form(""),
                                entry_point: str = Form(...),
                                commands_json_payload: str = Form("[]"),
                                source_files: List[UploadFile] = File(...)):
    user = require_admin(request)
    version = version.strip()
    entry_point = entry_point.strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]
    cursor.execute("SELECT id FROM asset_versions WHERE asset_id = ? AND version = ?", (actual_id, version))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="admin/version_deploy.html",
            context={
                "request": request,
                "user": user,
                "asset": dict(asset),
                "error": f"Version '{version}' is already deployed for this asset."
            }
        )

    slug = asset["slug"]
    commands_list = normalize_commands_payload(commands_json_payload)

    pkg_info = PackageService.build_package_bundle(
        slug, version, source_files, entry_point, commands_list, asset["name"]
    )

    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO asset_versions (asset_id, version, release_notes, download_url, file_size, sha256, commands_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (actual_id, version, release_notes.strip(), pkg_info["download_url"], pkg_info["file_size"], pkg_info["sha256"], json.dumps(commands_list), now))

    cursor.execute("""
    UPDATE assets SET latest_version = ?, commands_json = ?, updated_at = ? WHERE id = ?
    """, (version, json.dumps(commands_list), now, actual_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/admin/assets/{actual_id}/versions?success=Version+{version}+deployed+successfully", status_code=302)

@router.get("/assets/{asset_id}/versions/{version}/edit", response_class=HTMLResponse)
def edit_version_page(request: Request, asset_id: str, version: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]
    cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? AND version = ?", (actual_id, version.strip()))
    version_row = cursor.fetchone()
    conn.close()

    if not version_row:
        raise HTTPException(status_code=404, detail="Version not found.")

    raw_commands = []
    if version_row["commands_json"]:
        try:
            raw_commands = json.loads(version_row["commands_json"])
        except Exception:
            raw_commands = []

    version_dict = dict(version_row)
    version_dict["commands_list"] = raw_commands

    return templates.TemplateResponse(
        request=request,
        name="admin/version_edit.html",
        context={"request": request, "user": user, "asset": dict(asset), "version": version_dict, "error": None}
    )

@router.post("/assets/{asset_id}/versions/{version}/edit", response_class=HTMLResponse)
async def edit_version_action(request: Request,
                              asset_id: str,
                              version: str,
                              new_version: str = Form(...),
                              release_notes: str = Form(""),
                              entry_point: str = Form(""),
                              commands_json_payload: str = Form("[]"),
                              source_files: Optional[List[UploadFile]] = File([])):
    user = require_admin(request)
    old_version = version.strip()
    target_version = new_version.strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]

    if target_version != old_version:
        cursor.execute("SELECT id FROM asset_versions WHERE asset_id = ? AND version = ?", (actual_id, target_version))
        if cursor.fetchone():
            conn.close()
            cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? AND version = ?", (actual_id, old_version))
            v_curr = dict(cursor.fetchone())
            v_curr["commands_list"] = normalize_commands_payload(commands_json_payload)
            return templates.TemplateResponse(
                request=request,
                name="admin/version_edit.html",
                context={
                    "request": request,
                    "user": user,
                    "asset": dict(asset),
                    "version": v_curr,
                    "error": f"Version '{target_version}' already exists for this asset. Choose an unused version tag."
                }
            )

    commands_list = normalize_commands_payload(commands_json_payload)
    is_latest = (asset["latest_version"] == old_version)

    pkg_info = PackageService.update_version_package(
        slug=asset["slug"],
        old_version=old_version,
        new_version=target_version,
        files=source_files,
        entry_point=entry_point.strip(),
        commands=commands_list,
        asset_name=asset["name"],
        is_latest=is_latest
    )

    cursor.execute("""
    UPDATE asset_versions SET
        version = ?,
        release_notes = ?,
        download_url = ?,
        file_size = ?,
        sha256 = ?,
        commands_json = ?
    WHERE asset_id = ? AND version = ?
    """, (target_version, release_notes.strip(), pkg_info["download_url"], pkg_info["file_size"], pkg_info["sha256"], json.dumps(commands_list), actual_id, old_version))

    if is_latest or target_version != old_version:
        new_latest = target_version if is_latest else asset["latest_version"]
        cursor.execute("""
        UPDATE assets SET latest_version = ?, commands_json = ?, updated_at = ? WHERE id = ?
        """, (new_latest, json.dumps(commands_list), datetime.datetime.utcnow().isoformat(), actual_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/admin/assets/{actual_id}/versions?success=Version+{target_version}+updated+successfully", status_code=302)

@router.post("/assets/{asset_id}/versions/{version}/delete")
def delete_asset_version(request: Request, asset_id: str, version: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()

    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    actual_id = asset["id"]
    cursor.execute("DELETE FROM asset_versions WHERE asset_id = ? AND version = ?", (actual_id, version))
    cursor.execute("SELECT version, commands_json FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (actual_id,))
    remaining_rows = cursor.fetchall()
    remaining = [r["version"] for r in remaining_rows]

    new_latest = remaining[0] if remaining else ""
    new_commands = remaining_rows[0]["commands_json"] if remaining_rows else "[]"

    cursor.execute("UPDATE assets SET latest_version = ?, commands_json = ? WHERE id = ?", (new_latest, new_commands, actual_id))
    conn.commit()
    conn.close()

    PackageService.delete_version_archive(asset["slug"], version, remaining)
    return RedirectResponse(f"/admin/assets/{actual_id}/versions?success=Version+{version}+removed", status_code=302)

@router.post("/assets/{asset_id}/delete")
def delete_asset_action(request: Request, asset_id: str):
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
    asset = cursor.fetchone()
    if asset:
        actual_id = asset["id"]
        cursor.execute("DELETE FROM asset_versions WHERE asset_id = ?", (actual_id,))
        cursor.execute("DELETE FROM comments WHERE asset_id = ?", (actual_id,))
        cursor.execute("DELETE FROM assets WHERE id = ?", (actual_id,))
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
    commands_list = normalize_commands_payload(commands_json_payload)

    pkg_info = PackageService.build_package_bundle(
        slug, version.strip(), source_files, entry_point.strip(), commands_list, name.strip()
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
    user = require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/reviews", status_code=302)