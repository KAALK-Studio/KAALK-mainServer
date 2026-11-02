# app/routers/store_api.py
import json
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.database import get_db
from app.schemas import ReviewSubmissionRequest

router = APIRouter(prefix="/api/v1", tags=["AutoCAD Store API"])

@router.get("/catalog")
def get_catalog(type: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT id, slug, name, type, latest_version, min_autocad, short_desc,
           thumb_32_url, thumb_64_url, is_pro, rating, rating_count, dev_name,
           commands_json, tags
    FROM assets
    """
    params = ()
    if type:
        query += " WHERE type = ?"
        params = (type.lower().strip(),)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    assets = []
    for r in rows:
        thumb_url = r["thumb_64_url"] or r["thumb_32_url"] or f"/static/media/{r['slug']}/icon_64.png"
        rating_val = float(r["rating"]) if (r["rating_count"] and r["rating_count"] > 0 and r["rating"] is not None) else 0.0

        try:
            raw_commands = json.loads(r["commands_json"]) if r["commands_json"] else []
        except Exception:
            raw_commands = []

        cleaned_commands = []
        for c in raw_commands:
            if isinstance(c, dict) and c.get("command"):
                cleaned_commands.append({
                    "command": str(c.get("command", "")).strip().upper(),
                    "alias": str(c.get("alias", "")).strip().upper(),
                    "title": str(c.get("title", "")).strip(),
                    "status": str(c.get("status", "stable")).strip().lower(),
                    "description": str(c.get("description", "")).strip(),
                    "deprecation_notice": str(c.get("deprecation_notice", "")).strip()
                })

        assets.append({
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "type": r["type"],
            "version": r["latest_version"] or "1.0.0",
            "min_autocad": r["min_autocad"],
            "short_desc": r["short_desc"] or "",
            "thumb_url": thumb_url,
            "is_pro": bool(r["is_pro"]),
            "rating": rating_val,
            "dev": r["dev_name"] or "KAALK Studio",
            "commands": cleaned_commands,
            "tags": r["tags"] or ""
        })

    return {
        "catalog_version": "1.0",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_assets": len(assets),
        "assets": assets
    }

@router.get("/assets/{asset_id}")
def get_asset_detail(asset_id: str, version: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    cursor.execute("""
    SELECT version, release_notes, download_url, file_size, sha256, commands_json, created_at
    FROM asset_versions WHERE asset_id = ? ORDER BY id DESC
    """, (asset_id,))
    versions_rows = cursor.fetchall()

    version_history = []
    selected_version_data = None
    target_ver = version or asset["latest_version"]

    for v in versions_rows:
        try:
            raw_v_commands = json.loads(v["commands_json"]) if v["commands_json"] else []
        except Exception:
            raw_v_commands = []

        cleaned_v_commands = []
        for c in raw_v_commands:
            if isinstance(c, dict) and c.get("command"):
                cleaned_v_commands.append({
                    "command": str(c.get("command", "")).strip().upper(),
                    "alias": str(c.get("alias", "")).strip().upper(),
                    "title": str(c.get("title", "")).strip(),
                    "status": str(c.get("status", "stable")).strip().lower(),
                    "description": str(c.get("description", "")).strip(),
                    "deprecation_notice": str(c.get("deprecation_notice", "")).strip()
                })

        item = {
            "version": v["version"],
            "release_notes": v["release_notes"] or "",
            "download_url": v["download_url"],
            "file_size": v["file_size"],
            "sha256": v["sha256"],
            "commands": cleaned_v_commands,
            "created_at": v["created_at"]
        }
        version_history.append(item)
        if v["version"] == target_ver:
            selected_version_data = item

    if not selected_version_data and version_history:
        selected_version_data = version_history[0]

    cursor.execute("""
    SELECT author, text, rating, created_at 
    FROM comments 
    WHERE asset_id = ? 
    ORDER BY id DESC 
    LIMIT 20
    """, (asset_id,))
    comment_rows = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as count FROM comments WHERE asset_id = ?", (asset_id,))
    total_comments = cursor.fetchone()["count"]
    conn.close()

    try:
        media_list = json.loads(asset["media_json"]) if asset["media_json"] else []
    except Exception:
        media_list = []

    active_commands = selected_version_data["commands"] if (selected_version_data and selected_version_data.get("commands")) else []
    if not active_commands:
        try:
            raw_fallback = json.loads(asset["commands_json"]) if asset["commands_json"] else []
            active_commands = [
                {
                    "command": str(c.get("command", "")).strip().upper(),
                    "alias": str(c.get("alias", "")).strip().upper(),
                    "title": str(c.get("title", "")).strip(),
                    "status": str(c.get("status", "stable")).strip().lower(),
                    "description": str(c.get("description", "")).strip(),
                    "deprecation_notice": str(c.get("deprecation_notice", "")).strip()
                }
                for c in raw_fallback if isinstance(c, dict) and c.get("command")
            ]
        except Exception:
            active_commands = []

    return {
        "id": asset["id"],
        "slug": asset["slug"],
        "name": asset["name"],
        "full_description": asset["full_desc"] or "",
        "commands": active_commands,
        "developer": {
            "id": asset["dev_id"] or "dev_kaalk",
            "name": asset["dev_name"] or "KAALK Studio",
            "website": asset["dev_website"] or "https://kaalk.ir"
        },
        "stats": {
            "rating_count": asset["rating_count"] or 0,
            "download_count": asset["download_count"] or 0
        },
        "versions": {
            "latest": asset["latest_version"] or "1.0.0",
            "selected": selected_version_data["version"] if selected_version_data else (asset["latest_version"] or "1.0.0"),
            "available": [v["version"] for v in version_history]
        },
        "package": {
            "download_url": selected_version_data["download_url"] if selected_version_data else "",
            "file_size": selected_version_data["file_size"] if selected_version_data else 0,
            "sha256": selected_version_data["sha256"] if selected_version_data else ""
        },
        "release_notes": selected_version_data["release_notes"] if selected_version_data else "",
        "version_history": version_history,
        "media": media_list,
        "comments_summary": {
            "total_count": total_comments,
            "latest_comments": [
                {
                    "author": c["author"],
                    "text": c["text"],
                    "rating": c["rating"] or 0,
                    "created_at": c["created_at"][:10] if c["created_at"] else ""
                }
                for c in comment_rows
            ]
        },
        "updated_at": asset["updated_at"]
    }

@router.post("/assets/{asset_id}/reviews", status_code=status.HTTP_201_CREATED)
def post_asset_review(asset_id: str, payload: ReviewSubmissionRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    user_id = None
    if payload.email and payload.email.strip():
        cursor.execute("SELECT id FROM users WHERE email = ?", (payload.email.strip().lower(),))
        user_row = cursor.fetchone()
        if user_row:
            user_id = user_row["id"]

    now = datetime.datetime.utcnow().isoformat()
    submitted_rating = payload.rating if (payload.rating and 1 <= payload.rating <= 5) else None
    author_name = payload.author.strip() if payload.author else "You"

    existing_comment = None
    if user_id:
        cursor.execute("SELECT id FROM comments WHERE asset_id = ? AND user_id = ?", (asset_id, user_id))
        existing_comment = cursor.fetchone()
    if not existing_comment and payload.email:
        cursor.execute("SELECT id FROM comments WHERE asset_id = ? AND author = ?", (asset_id, payload.email.strip()))
        existing_comment = cursor.fetchone()
    if not existing_comment and author_name != "You":
        cursor.execute("SELECT id FROM comments WHERE asset_id = ? AND author = ?", (asset_id, author_name))
        existing_comment = cursor.fetchone()

    if existing_comment:
        cursor.execute("""
        UPDATE comments SET text = ?, rating = ?, created_at = ?, user_id = COALESCE(?, user_id), author = ?
        WHERE id = ?
        """, (payload.text.strip(), submitted_rating, now, user_id, author_name, existing_comment["id"]))
    else:
        cursor.execute("""
        INSERT INTO comments (asset_id, user_id, author, text, rating, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (asset_id, user_id, author_name, payload.text.strip(), submitted_rating, now))

    cursor.execute("""
    SELECT AVG(rating) as avg_rating, COUNT(rating) as count_rating 
    FROM comments 
    WHERE asset_id = ? AND rating IS NOT NULL AND rating > 0
    """, (asset_id,))
    stats_row = cursor.fetchone()
    calc_rating = round(float(stats_row["avg_rating"]), 1) if (stats_row and stats_row["avg_rating"] is not None) else 0.0
    calc_count = int(stats_row["count_rating"]) if (stats_row and stats_row["count_rating"] is not None) else 0

    cursor.execute("UPDATE assets SET rating = ?, rating_count = ? WHERE id = ?", (calc_rating, calc_count, asset_id))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Review recorded successfully.", "rating": calc_rating, "rating_count": calc_count}

@router.get("/user/reviews")
def get_user_reviews(email: Optional[str] = Query(None), author: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT c.id, c.asset_id, a.name as asset_name, c.rating, c.text, c.created_at
    FROM comments c
    JOIN assets a ON c.asset_id = a.id
    """
    conditions = []
    params = []

    if email and email.strip():
        clean_email = email.strip().lower()
        conditions.append("(c.user_id IN (SELECT id FROM users WHERE email = ?) OR c.author = ?)")
        params.extend([clean_email, clean_email])

    if author and author.strip() and author != "You":
        conditions.append("c.author = ?")
        params.append(author.strip())

    if conditions:
        query += " WHERE " + " OR ".join(conditions)

    query += " ORDER BY c.id DESC LIMIT 50"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    reviews = []
    for r in rows:
        reviews.append({
            "id": r["id"],
            "asset_id": r["asset_id"],
            "asset_name": r["asset_name"],
            "rating": r["rating"] or 0,
            "text": r["text"],
            "created_at": r["created_at"][:10] if r["created_at"] else ""
        })

    return {"reviews": reviews}

@router.post("/reviews/{review_id}/delete")
def delete_user_review(review_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT asset_id FROM comments WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if row:
        asset_id = row["asset_id"]
        cursor.execute("DELETE FROM comments WHERE id = ?", (review_id,))

        cursor.execute("""
        SELECT AVG(rating) as avg_rating, COUNT(rating) as count_rating 
        FROM comments 
        WHERE asset_id = ? AND rating IS NOT NULL AND rating > 0
        """, (asset_id,))
        stats_row = cursor.fetchone()
        calc_rating = round(float(stats_row["avg_rating"]), 1) if (stats_row and stats_row["avg_rating"] is not None) else 0.0
        calc_count = int(stats_row["count_rating"]) if (stats_row and stats_row["count_rating"] is not None) else 0
        cursor.execute("UPDATE assets SET rating = ?, rating_count = ? WHERE id = ?", (calc_rating, calc_count, asset_id))

    conn.commit()
    conn.close()
    return {"success": True}
